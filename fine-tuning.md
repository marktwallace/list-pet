# Fine-tuning with ft-pipe

`ft-pipe` is a command-line utility designed to streamline the process of fine-tuning OpenAI models, specifically optimized for use with exported conversations from the Streamlit interface.

## TL;DR
```bash
# Install
cd tools/ft-pipe
pip install .

# Run
ft-pipe prepare training/04-02-21-34
ft-pipe validate training/04-02-21-34/04-02-21-34.jsonl
ft-pipe upload training/04-02-21-34/04-02-21-34.jsonl
ft-pipe start file-abc123456
```

Use these tools with the OpenAI console. After "upload" go to:

https://platform.openai.com/storage

To see the uploaded file. After "start" go to:

https://platform.openai.com/finetune

To see progress.

## Installation

1. Clone the repository and navigate to the tools/ft-pipe directory:
   ```bash
   cd tools/ft-pipe
   ```

2. Install the package:
   ```bash
   pip install .
   ```

## Usage

The fine-tuning process consists of four main steps:

### 1. Prepare Data
Convert your exported .txt conversations into OpenAI's JSONL format:

```bash
ft-pipe prepare training/04-02-21-34
```

By default, the output file will be named after the input directory (e.g., `04-02-21-34.jsonl`). This helps track different training runs in the OpenAI console.

Options:
- `--output-file`: Override the default output filename if needed
- `--system-prompt`: Optional path to a file containing an alternate system prompt

### 2. Validate Data
Check format, count tokens, and estimate fine-tuning cost:

```bash
ft-pipe validate training/04-02-21-34/04-02-21-34.jsonl
```

This will display:
- Number of validated examples
- Total token count
- Estimated fine-tuning cost

### 3. Upload Data
Upload the JSONL file to OpenAI:

```bash
ft-pipe upload training/04-02-21-34/04-02-21-34.jsonl
```

This will return a file ID needed for the next step. You can view your uploaded files at:
https://platform.openai.com/storage

### 4. Start Fine-tuning
Launch the fine-tuning job:

```bash
ft-pipe start file-abc123456
```

Options:
- `--model`: Base model to fine-tune (default: gpt-4o-mini-2024-04-09)
- `--beta`: DPO beta hyperparameter (default: 0.1)

Monitor your fine-tuning job at: https://platform.openai.com/finetune

## Input Format

Each .txt file should contain a line-oriented conversation in the following format:

```
System:
[system prompt]
--- END EXAMPLE ---
[additional dynamic system lines, optional]
Assistant:
[response lines]
User:
[response lines]
Assistant:
[response lines]
```

- Each role (System/User/Assistant) must appear on its own line followed by a colon
- The system prompt section (from "System:" through "--- END EXAMPLE ---") can be replaced using the --system-prompt option
- Additional system messages can be added after the "--- END EXAMPLE ---" marker

## Output Format

The generated JSONL file will contain one JSON object per line, formatted as:

```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."},
    ...
  ]
}
``` 