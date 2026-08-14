import sys
import os
import json
import base64
import shutil
import logging

# Add the parent directory of svn_server to the Python path
# so svn_shared can be imported.
script_dir = os.path.dirname(__file__)
# svn_server/resources -> svn_server -> svn_util (which contains svn_shared)
svn_util_dir = os.path.abspath(os.path.join(script_dir, '..', '..'))
sys.path.insert(0, svn_util_dir)

from svn_shared.crash_handler import setup_logging
from svn_shared.config_parser import (
    write_passwd, PasswdEntry,
    AuthzRule, # Only needed for type hinting if we were parsing, but we'll write raw for authz
    write_svnserve_conf, SvnserveConfig,
    parse_svnserve_conf # Needed to get raw_lines for preserving comments
)

logger = logging.getLogger(__name__)

def _backup(path: str) -> str:
    """Create a .bak backup of a file."""
    bak = f"{path}.bak"
    if os.path.exists(path):
        shutil.copy2(path, bak)
        logger.debug("Backed up %s to %s", path, bak)
    return bak

def _write_file(file_type: str, file_path: str, data: str) -> None:
    """Writes a single config file based on its type."""
    logger.info("Writing %s file to %s", file_type, file_path)
    try:
        if file_type == "passwd":
            entries_data = json.loads(data)  # This is a list of dicts
            logger.debug("Parsing %d entries for passwd file.", len(entries_data))
            entries = [
                PasswdEntry(username=e['username'], password=e['password'], active=e.get('active', True))
                for e in entries_data
            ]
            write_passwd(file_path, entries) # write_passwd handles backup internally
            logger.info("Successfully wrote passwd file: %s", file_path)
        elif file_type == "authz":
            _backup(file_path) # Manual backup for authz as we're writing raw content
            with open(file_path, "w") as f:
                f.write(data)
            logger.info("Successfully wrote authz file: %s", file_path)
        elif file_type == "svnserve_conf":
            config_data = json.loads(data)
            logger.debug("Parsing svnserve.conf data: %s", config_data)
            
            # Parse existing config to preserve comments and structure
            existing_config = parse_svnserve_conf(file_path) if os.path.exists(file_path) else SvnserveConfig()
            
            # Update values from the received data
            existing_config.anon_access = config_data.get('anon-access', existing_config.anon_access) # type: ignore
            existing_config.auth_access = config_data.get('auth-access', existing_config.auth_access) # type: ignore
            existing_config.password_db = config_data.get('password-db', existing_config.password_db) # type: ignore
            existing_config.authz_db = config_data.get('authz-db', existing_config.authz_db) # type: ignore
            existing_config.realm = config_data.get('realm', existing_config.realm) # type: ignore

            write_svnserve_conf(file_path, existing_config) # write_svnserve_conf handles backup internally
            logger.info("Successfully wrote svnserve.conf file: %s", file_path)
        else:
            raise ValueError(f"Unknown file type: {file_type}")
    except Exception as e:
        # Re-raise to be caught in main and exit with an error code
        logger.error("Error writing config file %s (%s): %s", file_path, file_type, e, exc_info=True)
        raise

def _write_batch(file_type: str, batch_items: list) -> None:
    """Writes multiple config files of the same type in a single batch."""
    logger.info("Starting batch write for file_type: %s with %d items.", file_type, len(batch_items))
    for item in batch_items:
        file_path = item.get("path")
        raw_data = item.get("data") # This is the content (list of dicts for passwd, string for authz)

        if not file_path or raw_data is None:
            logger.error("Missing 'path' or 'data' in batch item: %s", item)
            raise ValueError(f"Missing 'path' or 'data' in batch item: {item}")

        # Prepare data for _write_file based on file_type
        data_to_write = ""
        if file_type == "passwd":
            # raw_data is a list of PasswdEntry dicts, needs to be JSON stringified
            data_to_write = json.dumps(raw_data)
            logger.debug("Prepared passwd data for %s.", file_path)
        elif file_type == "authz":
            # raw_data is already the authz content string
            data_to_write = raw_data
            logger.debug("Prepared authz data for %s.", file_path)
        elif file_type == "svnserve_conf":
            # raw_data is a dict, needs to be JSON stringified
            data_to_write = json.dumps(raw_data)
            logger.debug("Prepared svnserve_conf data for %s.", file_path)
        else:
            logger.error("Unknown file_type '%s' in _write_batch for path: %s", file_type, file_path)
            raise ValueError(f"Unknown file_type '{file_type}' in _write_batch.")

        _write_file(file_type, file_path, data_to_write)
    logger.info("Batch write for file_type '%s' completed successfully.", file_type)

def main():
    if len(sys.argv) < 3:
        print("Usage: python privileged_config_writer.py <action> <base64_data> [<path>] [<debug_level>]", file=sys.stderr)
        sys.exit(1)

    action = sys.argv[1]
    debug_level = 0

    # Setup logging early. The debug level is expected to be the last argument.
    try:
        if sys.argv[-1].isdigit():
            debug_level = int(sys.argv[-1])
    except (IndexError, ValueError):
        pass # default to 0
    
    setup_logging("svn-server-admin", debug_level)
    logger.debug("privileged_config_writer started with action: '%s', debug_level: %d", action, debug_level)
    try:
        if action == "batch_write":
            base64_data = sys.argv[2]
            decoded_data = base64.b64decode(base64_data).decode('utf-8')
            batch_data = json.loads(decoded_data)
            logger.debug("Batch write received with keys: %s", list(batch_data.keys()))

            for file_type, items_to_write in batch_data.items():
                if not isinstance(items_to_write, list):
                    logger.error("Expected a list of items for file_type '%s', got: %s", file_type, type(items_to_write).__name__)
                    raise ValueError(f"Expected a list of items for file_type '{file_type}'.")
                _write_batch(file_type, items_to_write)
            
            logger.info("All batch writes completed successfully.")
        else:
            # Handle single file write for backward compatibility or other uses
            file_type = action
            file_path = sys.argv[2]
            base64_data = sys.argv[3]
            decoded_data = base64.b64decode(base64_data).decode('utf-8')
            _write_file(file_type, file_path, decoded_data)

    except Exception as e:
        logger.critical("Unhandled exception in privileged_config_writer: %s", e, exc_info=True)
        print(f"Error: {e}", file=sys.stderr) # Also print for PkexecRunnerDialog
        sys.exit(1)

if __name__ == "__main__":
    main()