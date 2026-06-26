import logging
logger = logging.getLogger(__name__)
from pathlib import Path
import subprocess
import re

EMPTY_STATUS = re.compile(r'^Status against revision:', flags = re.IGNORECASE)
N_STATUS_COLUMNS = 9
TIMEOUT_DURATION = 60 * 5 # five minutes

def verify_status_clean(file: Path):
    command = ['svn', 'status', '-u', file]
    try:
        status = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=True,
            timeout=TIMEOUT_DURATION,
        )
    except FileNotFoundError as e:
        logger.critical(
            f"It appears svn is not installed. "
            "If you do not wish to perform svn operations, use `--no-svn`"
        )
        raise e
    except subprocess.CalledProcessError as e:
        logger.critical(
            f"svn returned non-zero exit status: {status.stderr}"
        )
        raise e
    except subprocess.TimeoutExpired as e:
        logger.critical(f"svn timed out (after {TIMEOUT_DURATION} seconds)")
        raise e    
    # if status -u only outputs the "Status against revision line" it's clean
    # to be extra safe, check that the file is not in the output either
    is_clean = (
        EMPTY_STATUS.match(status.stdout) is not None and
        str(file) not in status.stdout
    )
    if is_clean:
        return    
    columns = status.stdout[:N_STATUS_COLUMNS]
    # could check exactly why it's not clean, but that seems like overkill    
    if columns != ' ' * N_STATUS_COLUMNS:
        logger.critical(f"svn status columns are not blank")
        raise RuntimeError(f"{file} not clean: {status.stdout}")
    return

def commit(file: Path, message: str):
    command = ['svn', 'commit', '-m', message]
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_DURATION,
        )
    except subprocess.CalledProcessError as e:
        logger.critical(f"svn returned non-zero exit status: {result.stderr}")
        raise e
    except subprocess.TimeoutExpired as e:
        logger.critical(f"svn timed out (after {TIMEOUT_DURATION} seconds)")
        raise e
        
        
    
