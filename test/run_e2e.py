#!/usr/bin/env python3
"""
End-to-end test of the wp-migration tool with two real WordPress containers.

Spins up source + target WordPress sites via Docker Compose,
installs WP with test content on source, runs the migration, then verifies.
"""

import subprocess
import time
import sys
import os
from pathlib import Path

TEST_DIR = Path(__file__).parent
COMPOSE_FILE = TEST_DIR / "docker-compose.yml"
CONFIG_FILE = TEST_DIR / "config.test.yaml"


def log(msg):
    print(f"[test] {msg}", flush=True)


def run(cmd, **kwargs):
    log(f"Running: {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, check=True, **kwargs)


def run_allow_fail(cmd, **kwargs):
    log(f"Running (allow fail): {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, **kwargs)


def main():
    # ── Step 0: Clean up any previous run ──
    log("Cleaning up previous containers...")
    run_allow_fail(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "down", "-v"],
        capture_output=True,
    )

    # ── Step 1: Start the containers ──
    log("Starting containers...")
    run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d", "--build"],
        timeout=300,
    )

    # Wait for WordPress to be ready
    log("Waiting for WordPress to become ready...")
    for i in range(60):
        r = run_allow_fail(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "http://localhost:8084"],
            capture_output=True, text=True,
        )
        if r.returncode == 0 and r.stdout.strip() == "200":
            log("Source WordPress is ready!")
            break
        time.sleep(5)
    else:
        log("FAILED: Source WordPress did not start in time")
        sys.exit(1)

    # Wait for target
    for i in range(30):
        r = run_allow_fail(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "http://localhost:8085"],
            capture_output=True, text=True,
        )
        if r.returncode == 0 and r.stdout.strip() == "200":
            log("Target WordPress is ready!")
            break
        time.sleep(3)
    else:
        log("FAILED: Target WordPress did not start in time")
        sys.exit(1)

    # Wait for SSH on both containers
    log("Waiting for SSH...")
    time.sleep(10)

    # ── Step 2: Install WP-CLI in source container ──
    log("Installing WP-CLI on source...")
    run(["docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T", "source-wp",
         "bash", "-c",
         "curl -sO https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar "
         "&& chmod +x wp-cli.phar && mv wp-cli.phar /usr/local/bin/wp"], timeout=60)

    # ── Step 3: Install WordPress on source ──
    log("Installing WordPress on source...")
    run(["docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T", "source-wp",
         "wp", "core", "install",
         "--url=http://localhost:8084",
         "--title=Source Site",
         "--admin_user=admin",
         "--admin_password=admin123",
         "--admin_email=admin@example.com"], timeout=60)

    # ── Step 4: Create test content ──
    log("Creating test content...")

    # Create posts with some content
    run(["docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T", "source-wp",
         "wp", "post", "create",
         "--post_title=Welcome to Source",
         "--post_content=This is the <strong>source site</strong> with some content.",
         "--post_status=publish"], timeout=30)

    run(["docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T", "source-wp",
         "wp", "post", "create",
         "--post_title=About Us",
         "--post_content=We are migrating from one host to another using wp-migration tool.",
         "--post_status=publish"], timeout=30)

    # Update site tagline (stored in wp_options, serialized context)
    run(["docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T", "source-wp",
         "wp", "option", "update", "blogdescription", "Migrating from source to target"], timeout=15)

    # Install and activate a simple plugin (Hello Dolly is bundled with WP)
    run(["docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T", "source-wp",
         "wp", "plugin", "activate", "hello"], timeout=15)

    # Create a navigation menu (tests serialized data)
    run(["docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T", "source-wp",
         "wp", "menu", "create", "Main Menu"], timeout=15)

    # Add a custom link to the menu
    run(["docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T", "source-wp",
         "wp", "menu", "item", "add-custom", "Main Menu",
         "Source Home", "http://localhost:8084"], timeout=15)

    # Upload a media file
    run(["docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T", "source-wp",
         "bash", "-c",
         "echo 'test image content' > /tmp/test-image.txt "
         "&& wp media import /tmp/test-image.txt --title='Test File'"],
        timeout=30)

    # Take a DB snapshot for reference
    log("Taking source DB snapshot...")
    run(["docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T", "source-db",
         "mysqldump", "-u", "wp_user", "-pwp_pass", "wp_source"],
        stdout=open(TEST_DIR / "source-snapshot.sql", "w"), timeout=30)

    # ── Step 5: Run the migration ──
    log("\n" + "=" * 60)
    log("RUNNING MIGRATION...")
    log("=" * 60 + "\n")

    result = subprocess.run(
        ["wp-migrate", "run", str(CONFIG_FILE)],
        capture_output=True, text=True, timeout=300,
    )
    log("Migration stdout:")
    print(result.stdout)
    if result.stderr:
        log("Migration stderr:")
        print(result.stderr)
    if result.returncode != 0:
        log(f"Migration returned non-zero exit code: {result.returncode}")
    else:
        log("Migration completed successfully!")

    # ── Step 6: Verify on target ──
    log("\n" + "=" * 60)
    log("VERIFYING MIGRATION...")
    log("=" * 60 + "\n")

    log("Installing WP-CLI on target...")
    run(["docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T", "target-wp",
         "bash", "-c",
         "curl -sO https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar "
         "&& chmod +x wp-cli.phar && mv wp-cli.phar /usr/local/bin/wp"], timeout=60)

    # Check posts migrated
    log("\n--- Posts on target ---")
    run(["docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T", "target-wp",
         "wp", "post", "list", "--format=table"], timeout=15)

    # Check options migrated (siteurl should be updated to new URL)
    log("\n--- Site options on target ---")
    run(["docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T", "target-wp",
         "wp", "option", "get", "siteurl"], timeout=15)
    run(["docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T", "target-wp",
         "wp", "option", "get", "blogdescription"], timeout=15)

    # Check plugins
    log("\n--- Active plugins on target ---")
    run(["docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T", "target-wp",
         "wp", "plugin", "list", "--format=table"], timeout=15)

    # Check menu
    log("\n--- Menus on target ---")
    run(["docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T", "target-wp",
         "wp", "menu", "list", "--format=table"], timeout=15)

    # Check media
    log("\n--- Media on target ---")
    run(["docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T", "target-wp",
         "wp", "post", "list", "--post_type=attachment", "--format=table"], timeout=15)

    # Verify the site actually loads
    log("\n--- Target site HTTP check ---")
    r = run_allow_fail(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "http://localhost:8085"],
        capture_output=True, text=True,
    )
    log(f"Target site HTTP status: {r.stdout.strip()}")

    # ── Step 7: Summary ──
    log("\n" + "=" * 60)
    log("TEST COMPLETE")
    log("=" * 60)

    # Leave containers running so user can inspect
    log("\nContainers are still running. To stop them:")
    log(f"  docker compose -f {COMPOSE_FILE} down -v")


if __name__ == "__main__":
    main()
