import json
import re
from pathlib import Path
from typing import Optional
import typer
import tiktoken
from openai import OpenAI

app = typer.Typer()

SYSTEM_ROLE = "system"
USER_ROLE = "user"
ASSISTANT_ROLE = "assistant"

ROLE_PATTERN = re.compile(r"^(System|User|Assistant):\s*$", re.IGNORECASE)
END_EXAMPLE_LINE = "--- END EXAMPLE ---"


def parse_txt_file(filepath: Path, replacement_system_prompt: Optional[str] = None) -> Optional[dict]:
    with filepath.open("r", encoding="utf-8") as f:
        lines = [line.rstrip("\n") for line in f]

    messages = []
    current_role = None
    buffer = []
    system_buffer = []
    after_end_example = []
    found_end_example = False

    for line in lines:
        role_match = ROLE_PATTERN.match(line)
        if role_match:
            if current_role:
                content = "\n".join(buffer).strip()
                if current_role.lower() == SYSTEM_ROLE:
                    if not found_end_example:
                        system_buffer.append(content)
                    else:
                        after_end_example.append(content)
                else:
                    messages.append({"role": current_role.lower(), "content": content})
                buffer = []

            current_role = role_match.group(1).capitalize()
        elif line.strip() == END_EXAMPLE_LINE:
            found_end_example = True
            buffer.append(line)
        else:
            buffer.append(line)

    if current_role and buffer:
        content = "\n".join(buffer).strip()
        if current_role.lower() == SYSTEM_ROLE:
            if not found_end_example:
                system_buffer.append(content)
            else:
                after_end_example.append(content)
        else:
            messages.append({"role": current_role.lower(), "content": content})

    if not messages:
        typer.echo(f"Warning: No messages found in {filepath.name}, skipping.")
        return None

    if replacement_system_prompt:
        with open(replacement_system_prompt, "r", encoding="utf-8") as sp:
            system_text = sp.read().strip()
    else:
        system_text = "\n".join(system_buffer).strip()

    if after_end_example:
        system_text += "\n" + "\n".join(after_end_example).strip()

    all_messages = [{"role": SYSTEM_ROLE, "content": system_text}] + messages
    return {"messages": all_messages}


@app.command()
def prepare(
    input_dir: Path = typer.Argument(..., exists=True, file_okay=False, help="Directory with .txt files"),
    output_file: Path = typer.Option(None, help="Output .jsonl filename (defaults to directory name)"),
    system_prompt: Optional[Path] = typer.Option(None, help="Optional alternate system prompt file")
):
    """Convert a directory of .txt conversations into a single OpenAI-compatible .jsonl file."""
    txt_files = sorted(input_dir.glob("*.txt"))
    if not txt_files:
        typer.echo("No .txt files found.")
        raise typer.Exit()

    examples = []
    for txt_file in txt_files:
        parsed = parse_txt_file(txt_file, replacement_system_prompt=str(system_prompt) if system_prompt else None)
        if parsed:
            examples.append(parsed)

    if not examples:
        typer.echo("No valid training examples found. Exiting.")
        raise typer.Exit()

    # Use directory name as default filename
    if output_file is None:
        output_file = Path(f"{input_dir.name}.jsonl")
    
    output_path = input_dir / output_file

    with output_path.open("w", encoding="utf-8") as out:
        for example in examples:
            out.write(json.dumps(example, ensure_ascii=False) + "\n")

    typer.echo(f"Wrote {len(examples)} examples to {output_path}")


@app.command()
def validate(
    jsonl_file: Path = typer.Argument(..., exists=True, file_okay=True, help="Path to the .jsonl file")
):
    """Validate format and estimate token count and cost."""
    try:
        enc = tiktoken.encoding_for_model("gpt-4o")
    except Exception:
        enc = tiktoken.get_encoding("cl100k_base")

    total_tokens = 0
    example_count = 0

    with jsonl_file.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            try:
                obj = json.loads(line)
                assert "messages" in obj
                assert isinstance(obj["messages"], list)
                for msg in obj["messages"]:
                    assert "role" in msg and "content" in msg
                    total_tokens += len(enc.encode(msg["content"]))
                example_count += 1
            except Exception as e:
                typer.echo(f"Error on line {line_num}: {e}")
                raise typer.Exit(code=1)

    # GPT-4o mini pricing (per 1M tokens)
    TRAINING_COST_PER_1M = 3.00  # $3.00 per 1M tokens for training
    INPUT_COST_PER_1M = 0.30     # $0.30 per 1M tokens for input
    CACHED_INPUT_COST_PER_1M = 0.15  # $0.15 per 1M tokens for cached input
    OUTPUT_COST_PER_1M = 1.20    # $1.20 per 1M tokens for output

    # Calculate training cost
    training_cost = total_tokens / 1_000_000 * TRAINING_COST_PER_1M
    input_cost = total_tokens / 1_000_000 * INPUT_COST_PER_1M
    cached_input_cost = total_tokens / 1_000_000 * CACHED_INPUT_COST_PER_1M

    typer.echo(f"Validated {example_count} examples.")
    typer.echo(f"Total tokens: {total_tokens:,}")
    typer.echo("\nEstimated costs:")
    typer.echo(f"Training cost: ${training_cost:,.4f}")
    typer.echo(f"Input cost (first run): ${input_cost:,.4f}")
    typer.echo(f"Input cost (subsequent runs): ${cached_input_cost:,.4f}")
    typer.echo(f"\nNote: Output costs ($1.20 per 1M tokens) will apply when using the model.")


@app.command()
def upload(
    jsonl_file: Path = typer.Argument(..., exists=True, file_okay=True, help="Path to .jsonl file to upload")
):
    """Upload the .jsonl file to OpenAI for fine-tuning."""
    client = OpenAI()
    with jsonl_file.open("rb") as f:
        upload = client.files.create(file=f, purpose="fine-tune")
    typer.echo(f"Uploaded {jsonl_file.name}. File ID: {upload.id}")


@app.command()
def start(
    file_id: str = typer.Argument(..., help="Uploaded file ID returned by the upload step"),
    model: str = typer.Option("gpt-4o-mini-2024-04-09", help="Base model to fine-tune"),
    beta: float = typer.Option(0.1, help="DPO beta hyperparameter")
):
    """Start a fine-tuning job using the uploaded training file."""
    client = OpenAI()
    job = client.fine_tuning.jobs.create(
        training_file=file_id,
        model=model,
        method={
            "type": "dpo",
            "dpo": {
                "hyperparameters": {"beta": beta},
            },
        },
    )
    typer.echo(f"Started fine-tuning job. ID: {job.id}")
    typer.echo(f"Model: {job.model}")
    typer.echo("Monitor at: https://platform.openai.com/finetune")


if __name__ == "__main__":
    app()
