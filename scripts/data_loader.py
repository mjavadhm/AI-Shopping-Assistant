import os
import pandas as pd
from sqlalchemy import create_engine, inspect
import time
import json
import numpy as np


from app.core.logger import logger
from app.core.config import settings


DATA_DIR = "./data"

def get_db_engine():
    """Establishes a connection to the database with a retry mechanism."""
    if not settings.DATABASE_URL:
        logger.error("❌ DATABASE_URL environment variable is not set.")
        return None
        
    for attempt in range(5):
        try:
            engine = create_engine(settings.DATABASE_URL)
            with engine.connect():
                logger.info("✅ Database connection successful.")
                return engine
        except Exception as e:
            logger.warning(f"⏳ Database connection failed. Retrying in 3 seconds... (Attempt {attempt + 1}/5, Error: {e})")
            time.sleep(3)
    
    logger.critical("❌ Failed to connect to the database after multiple attempts.")
    return None

def load_parquet_files(engine):

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    logger.info(f"Tables already present in the database: {existing_tables}")

    for filename in os.listdir(DATA_DIR):
        if filename.endswith(".parquet"):
            table_name = os.path.splitext(filename)[0].lower()

            
            if table_name in existing_tables:
                logger.info(f"⏭️ Table '{table_name}' already exists. Skipping file.")
                continue  

            file_path = os.path.join(DATA_DIR, filename)
            logger.info(f"Processing file: {filename}...")
            
            try:
                df = pd.read_parquet(file_path)
                
                
                for col in df.columns:
                    
                    if df[col].dtype == 'object':
                        
                        if any(isinstance(i, np.ndarray) for i in df[col].dropna()):
                            logger.info(f"Converting numpy arrays in column '{col}' to JSON strings.")
                            
                            df[col] = df[col].apply(lambda x: json.dumps(x.tolist()) if isinstance(x, np.ndarray) else x)

                logger.info(f"Importing data into table: '{table_name}'...")
                df.to_sql(
                    table_name,
                    engine,
                    if_exists='replace', 
                    index=False,
                    chunksize=10000
                )
                logger.info(f"✅ Successfully imported data into table: '{table_name}'.")
            except Exception as e:
                logger.error(f"❌ Failed to import data for table '{table_name}'. Error: {e}")

if __name__ == "__main__":
    logger.info("--- Starting data loading script ---")
    db_engine = get_db_engine()
    if db_engine:
        load_parquet_files(db_engine)
        db_engine.dispose()
    logger.info("--- Data loading script finished ---")