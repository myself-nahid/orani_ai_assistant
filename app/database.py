# In app/database.py

from sqlmodel import create_engine, SQLModel
from sqlalchemy import text # <--- IMPORT 'text'

DATABASE_URL = "sqlite:///orani_data.db" 

engine = create_engine(DATABASE_URL, echo=True) 

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

# --- START: ADD THIS NEW FUNCTION ---
def manually_add_structured_summary_column():
    """
    A simple, one-time-use function to add the missing column
    to an existing database without deleting it.
    """
    try:
        with engine.connect() as connection:
            # The SQL command to add a new column to the table
            # "IF NOT EXISTS" is not standard in SQLite's ALTER TABLE,
            # so we just run the command. If the column exists, it will error harmlessly.
            command = text("ALTER TABLE callsummarydb ADD COLUMN structured_summary JSON")
            connection.execute(command)
            # The 'commit' is needed to save the change
            connection.commit()
        print("--- Successfully added or verified 'structured_summary' column in 'callsummarydb' table. ---")
    except Exception as e:
        # This will likely happen if the column already exists, which is fine.
        print(f"--- Info: Could not add column, it likely already exists. Error: {e} ---")
# --- END: ADD THIS NEW FUNCTION ---