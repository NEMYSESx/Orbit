from typing import Dict
import asyncio
import json
from pathlib import Path
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

from config import get_settings

INGESTION_PIPELINE_PATH = str(Path(__file__).resolve().parent.parent.parent.parent / "ingestion-pipeline" / "ingestion-pipeline.exe")

async def process_document(file_path: str) -> Dict:
    try:
        settings = get_settings()
        print(f"Starting document processing for: {file_path}")
        print(f"Using Tika server at: {settings.TIKA_SERVER_URL}")
        
        config = {
            "tika": {
                "server_url": settings.TIKA_SERVER_URL,
                "timeout": settings.TIMEOUT,  
                "retry_attempts": settings.RETRY_ATTEMPTS,
                "retry_delay": settings.RETRY_DELAY 
            },
            "storage": {
                "output_dir": settings.OUTPUT_DIR,
                "temp_dir": settings.TEMP_DIR,
                "keep_originals": settings.KEEP_ORIGNALS,
                "compress_output": settings.COMPRESS_OUTPUT
            },
            "processing": {
                "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
                "supported_formats": settings.INPUT_FORMAT,
                "batch_size": settings.BATCH_SIZE,
                "max_concurrency": settings.MAX_CONCURRENCY,
                "enable_text_cleaning": settings.ENABLE_TEXT_CLEANING
            },
            "chunking": {
                "enabled": settings.ENABLE_CHUNKING,
                "gemini_api_key": settings.GEMINI_API_KEY,
                "gemini_model": settings.GEMINI_MODEL,
                "max_tokens": settings.GEMINI_MAX_TOKENS,
                "temperature": settings.GEMINI_TEMPERATURE
            }
        }
        
        config_path = os.path.join(os.path.dirname(file_path), "temp_config.json")
        with open(config_path, "w") as f:
            json_str = json.dumps(config, indent=4)
            print(f"Writing config to file:\n{json_str}")
            f.write(json_str)
        print(f"Created temporary config file at: {config_path}")

        try:
            if not os.path.exists(INGESTION_PIPELINE_PATH):
                raise FileNotFoundError(f"Ingestion pipeline executable not found at: {INGESTION_PIPELINE_PATH}")

            cmd = [
                INGESTION_PIPELINE_PATH,
                "-config", config_path,
                "-file", file_path,
                "-chunk", str(settings.ENABLE_CHUNKING).lower()
            ]
            print(f"Executing command: {' '.join(cmd)}")
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as pool:
                process = await loop.run_in_executor(
                    pool,
                    lambda: subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1,
                        universal_newlines=True
                    )
                )

                async def read_output(pipe, prefix):
                    while True:
                        line = await loop.run_in_executor(pool, pipe.readline)
                        if not line:
                            break
                        if prefix == "stdout":
                            print(f"Pipeline: {line.strip()}")
                        else:
                            line_lower = line.strip().lower()
                            if "error" in line_lower and ("failed" in line_lower or "exception" in line_lower):
                                print(f"Pipeline Error: {line.strip()}")
                            else:
                                print(f"Pipeline: {line.strip()}")

                stdout_task = asyncio.create_task(read_output(process.stdout, "stdout"))
                stderr_task = asyncio.create_task(read_output(process.stderr, "stderr"))

                await asyncio.gather(stdout_task, stderr_task)
                returncode = await loop.run_in_executor(pool, process.wait)

                if returncode != 0:
                    print(f"Pipeline failed with return code: {returncode}")
                    return {
                        "success": False,
                        "error": "Pipeline execution failed"
                    }

            print("Document processing completed successfully")
            return {
                "success": True,
                "document_id": Path(file_path).stem,
                "output_path": settings.OUTPUT_DIR
            }

        finally:
            if os.path.exists(config_path):
                os.remove(config_path)
                print(f"Cleaned up temporary config file: {config_path}")

    except Exception as e:
        print("Error during document processing")
        return {
            "success": False,
            "error": f"Processing error: {str(e)}"
        } 