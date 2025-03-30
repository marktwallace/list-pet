# list-pet: A Data Analysis Assistant

Talk with "List Pet" using a Streamlit-based UI reminiscent of ChatGPT. Unlike most LLM chat tools, List Pet has its own SQL database and a solid understanding of Plotly charts. It can import and manipulate large datasets using a local instance of DuckDB.

## Philosophy of Design

This project provides an open-source example of a structured, agentic AI system built around real-time interaction, local data tools, and well-defined flow control. It uses Streamlit for the user interface, DuckDB for data management, and a tag-based message format to structure reasoning, SQL actions, results, and error handling.

Messages are exchanged using a clear, inspectable format with tags like `<reasoning>`, `<sql>`, `<dataframe>`, and `<error>`, which allows both the human and the model to work with shared context and explicit actions. This structured approach makes the system easier to trace, debug, and extend.

The current implementation uses OpenAI's `gpt-4o-mini` due to its low cost and high capability. This model is accessed through the standard LangChain chat interface and responds to structured prompts with tagged outputs that can be interpreted and executed by the application.

In the future, we plan to migrate back to local models using Ollama once a cost-effective fine-tuning workflow is available. The system has been designed from the beginning to support that transition with minimal changes.

The goal is to provide a working example that is:
- Small enough to understand and modify
- Clear enough to serve as a starting point for similar agents
- Compatible with both remote and local LLMs

This project may serve as a foundation for experimentation with more advanced agent behaviors, memory strategies, or fine-tuned models.

## Example Conversation

Only the LLM completions are tagged as role `"Assistant"`; all other messages, including automatic outputs like `<dataframe>` and `<figure>`, are tagged as role `"User"`.

```plaintext
User:
Make a grocery list

Assistant:
<reasoning>
    We need a new grocery list table. Reasonable columns for a minimal grocery list could be item name, quantity, and category.
</reasoning>
<sql>
    CREATE TABLE grocery_list (
      item_name TEXT,
      quantity INTEGER,
      category TEXT);
</sql>
Creating a new grocery list table.

User:
Add milk, eggs, bread, jam

Assistant:
<reasoning>
    I will insert the items into the grocery list table. I'll assume a quantity of 1 for each item and categorize them as "Dairy" for milk and eggs, "Bakery" for bread, and "Condiments" for jam.
</reasoning>
<sql>
    INSERT INTO grocery_list (item_name, quantity, category) VALUES
    ('Milk', 1, 'Dairy'),
    ('Eggs', 1, 'Dairy'),
    ('Bread', 1, 'Bakery'),
    ('Jam', 1, 'Condiments');
</sql>
<sql>
    SELECT * FROM grocery_list;
</sql>
Items added to the grocery list.

User:
<dataframe name="grocery_list_1" table="grocery_list" sql_msg_idx="4" sql_tag_idx="1" >
item_name	quantity	category
Milk	1	Dairy
Eggs	1	Dairy
Bread	1	Bakery
Jam	1	Condiments
</dataframe>

User:
Show a pie chart by category

Assistant:
<reasoning>
    The user wants to visualize the distribution of grocery items across different categories using a pie chart. I will count the number of items in each category and create the pie chart with this data.
</reasoning>
<sql>
    SELECT
      category,
      COUNT(*) as item_count
    FROM grocery_list
    GROUP BY category
    ORDER BY item_count DESC;
</sql>
<chart dataframe="grocery_list">
    type: pie
    labels: category
    values: item_count
    title: Distribution of Grocery Items by Category
    hole: 0.3
</chart>
Here's a pie chart showing the distribution of grocery items across different categories in your list.

User:
<dataframe name="grocery_list_2" table="grocery_list" sql_msg_idx="7" sql_tag_idx="0" >
category	item_count
Dairy	2
Bakery	1
Condiments	1
</dataframe>

User:
<figure dataframe="grocery_list_2" sql_msg_idx="7" sql_tag_idx="0" chart_msg_idx="7" chart_tag_idx="0">
Distribution of Grocery Items by Category
</figure>
```

This example demonstrates how reasoning, SQL execution, result inspection, and visualization are cleanly separated and fully traceable in the system.

## Implementation Notes

The Cursor IDE was used to develop this project. Except for an initial prototype that had to be discarded, there wasn't any "vibe coding." In fact, around 1000 lines of code were written before allowing an LLM to suggest changes. Code brevity was prioritized, and LLM-generated additions are carefully reviewed.

For reference, the discarded prototype ballooned to ~10,000 lines within three days and became unmaintainable. The current version is holding at around 2000 lines of Python and remains clean and manageable.

The files are longer than ideal, but Cursor makes fewer mistakes with fewer, longer files.

## Building and Running

### Conda Setup

You will need Conda. To install Conda safely on a Mac:

```bash
brew install conda
conda init zsh
conda config --set auto_activate_base false
```

This ensures Conda doesn’t override your system Python and only activates in virtual environments.

To create a virtual environment:

```bash
conda create -p venv python=3.10
```

### The Python Project

Clone the repo:

```bash
git clone <repo_url>
cd ut-r1-langchain
```

Create and activate the virtual environment:

```bash
conda create -p venv python=3.10
conda activate ./venv
pip install -r requirements.txt
```

If Python packages have drifted, you may need:

```bash
pip install -r requirements_version.txt
```

`requirements_version.txt` was captured as of Feb 2025 using:

```bash
pip freeze > requirements_version.txt
```

### Running the App

Start Streamlit:

```bash
streamlit run app.py
```

The app will create a local database at `db/list_pet.db`. You can delete or move this file to reset the database (useful for testing).

**TODO:** Add CLI parameter to select or override the database path.

Data is stored in DuckDB tables. The message history is stored in a separate `pet-meta` schema, which includes all saved conversations.

**TODO:** Build CLI tools to export fine-tuning data from saved conversations.

---

### Old Ollama Pattern (currently not in use)

To run a local model (if/when re-enabled):

```bash
ollama serve
ollama run deepseek-r1:1.5b
```

