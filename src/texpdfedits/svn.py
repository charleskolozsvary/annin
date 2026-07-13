import logging
logger = logging.getLogger(__name__)
from pathlib import Path
import subprocess
import re

EMPTY_STATUS = re.compile(r'^Status against revision:', flags = re.IGNORECASE)
TIMEOUT_DURATION = 60 * 5 # five minutes

def verify_status_clean(file: Path):
    logger.info(f"Verifying {file} is clean in svn working directory...")
    command = ['svn', 'status', '-u', file.name]
    status = None
    try:
        status = subprocess.run(
            command,
            cwd=file.parent,
            text=True,
            capture_output=True,
            check=True,
            timeout=TIMEOUT_DURATION,
        )
    except FileNotFoundError as e:
        logger.critical(
            f"It appears svn is not installed: {e} "
            "If you do not wish to perform svn operations, use `--no-svn`"
        )
        raise
    except subprocess.CalledProcessError as e:
        logger.critical(
            "svn returned non-zero exit status (%s): %s",
            e.returncode,
            e.stderr or e.stdout,
        )
        raise
    except subprocess.TimeoutExpired:
        logger.critical(f"svn timed out (after {TIMEOUT_DURATION} seconds)")
        raise
    # if status -u only outputs the "Status against revision line", it's clean
    # to be extra safe, check that the file is not in the output either
    is_clean = (
        EMPTY_STATUS.match(status.stdout) is not None and
        file.name not in status.stdout
    )
    if is_clean:
        logger.info("Done")        
        return
        
    raise RuntimeError(
        f"{file} is not clean in svn working directory:\n{status.stdout}"
    )

def commit(file: Path, message: str):
    command = ['svn', 'commit', file.name, '-m', message]
    logger.info(f"Committing {file}...")
    try:
        subprocess.run(
            command,
            cwd=file.parent,
            check=True,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_DURATION,
        )
    except FileNotFoundError as e:
        logger.critical(
            f"It appears svn is not installed: {e} "
            "If you do not wish to perform svn operations, use `--no-svn`"
        )
        raise
    except subprocess.CalledProcessError as e:
        logger.critical(
            "svn returned non-zero exit status (%s): %s",
            e.returncode,
            e.stderr or e.stdout,
        )
        raise
    except subprocess.TimeoutExpired:
        logger.critical(f"svn timed out (after {TIMEOUT_DURATION} seconds)")
        raise
    logger.info("Done")
        
        
    
