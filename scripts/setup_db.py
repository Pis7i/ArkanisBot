import os
import sys
import subprocess
import getpass

def run_psql_command(command, as_postgres=True, ignore_errors=False):
    """Run a PostgreSQL command"""
    user = 'postgres' if as_postgres else 'arkanisbot'
    try:
        process = subprocess.Popen(
            ['psql', '-U', user, '-c', command],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate()
        if process.returncode != 0 and not ignore_errors:
            error_msg = stderr.decode() if hasattr(stderr, 'decode') else stderr
            if "already exists" not in error_msg or not ignore_errors:
                print("Error executing command:", error_msg)
                return False
        return True
    except Exception as e:
        print("Failed to execute command:", str(e))
        return False

def main():
    """Set up PostgreSQL database and user"""
    try:
        # Create database user (ignore if already exists)
        password = getpass.getpass("Enter password for database user 'arkanisbot': ")
        create_user = "CREATE USER arkanisbot WITH PASSWORD '{0}';".format(password)
        run_psql_command(create_user, ignore_errors=True)

        # Create database (ignore if already exists)
        create_db = "CREATE DATABASE arkanisbot OWNER arkanisbot;"
        run_psql_command(create_db, ignore_errors=True)

        # Grant privileges
        grant_privileges = "GRANT ALL PRIVILEGES ON DATABASE arkanisbot TO arkanisbot;"
        run_psql_command(grant_privileges)

        # Update .env file
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
        db_url = "postgresql://arkanisbot:{0}@localhost:5432/arkanisbot".format(password)
        
        # Read existing .env content
        env_content = ""
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                env_content = f.read()

        # Update DATABASE_URL if it exists, otherwise append it
        if 'DATABASE_URL=' in env_content:
            lines = env_content.splitlines()
            new_lines = []
            for line in lines:
                if line.startswith('DATABASE_URL='):
                    new_lines.append('DATABASE_URL="{0}"'.format(db_url))
                else:
                    new_lines.append(line)
            env_content = '\n'.join(new_lines)
        else:
            env_content += '\nDATABASE_URL="{0}"'.format(db_url)

        # Write updated .env file
        with open(env_path, 'w') as f:
            f.write(env_content)

        print("Database setup completed successfully!")
        print("You can now run: python scripts/init_db.py")

    except Exception as e:
        print("Failed to set up database:", str(e))
        raise

if __name__ == "__main__":
    main() 