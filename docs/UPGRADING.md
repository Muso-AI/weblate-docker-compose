# Upgrading from Upstream

This repository is a fork with custom modifications. Follow these steps to pull updates from the original WeblateOrg repository while preserving your custom module.

## Step 1: Fetch Latest Changes

```bash
git fetch upstream
```

This downloads the latest changes from the upstream repository without modifying your local files.

## Step 2: Check Current Status

Make sure you're on the main branch and have no uncommitted changes:

```bash
git status
```

If you have uncommitted changes, commit or stash them first:

```bash
# Option 1: Commit your changes
git add .
git commit -m "Your commit message"

# Option 2: Stash your changes (if not ready to commit)
git stash
```

## Step 3: Switch to Main Branch

```bash
git checkout main
```

## Step 4: Merge Upstream Changes

```bash
git merge upstream/main
```

This merges the upstream changes into your local main branch.

**If there are no conflicts:**
- The merge will complete automatically
- Your custom `machinery_custom/` directory will be preserved
- Proceed to Step 5

**If there are conflicts:**
- Git will mark the conflicted files
- Your custom module should be safe (it's unique to your fork)
- Resolve conflicts manually:
  ```bash
  # Check which files have conflicts
  git status
  
  # Edit conflicted files and resolve conflicts
  # Then mark them as resolved:
  git add <resolved-file>
  
  # Complete the merge:
  git commit
  ```

For detailed conflict resolution, see [Troubleshooting](TROUBLESHOOTING.md#merge-conflicts-during-upgrade).

## Step 5: Push to Your Fork

After successfully merging:

```bash
git push origin main
```

## Step 6: Update Docker Images (Optional)

After pulling upstream changes, you may want to update Docker images:

```bash
docker compose pull
docker compose up -d
```

## Quick Upgrade Script

You can create a script to automate the upgrade process. Create `upgrade.sh`:

```bash
#!/bin/bash
set -e

echo "Fetching upstream changes..."
git fetch upstream

echo "Checking out main branch..."
git checkout main

echo "Merging upstream/main..."
git merge upstream/main

echo "Pushing to origin..."
git push origin main

echo "Upgrade complete!"
echo "To update Docker images, run: docker compose pull && docker compose up -d"
```

Make it executable:

```bash
chmod +x upgrade.sh
```

Run it:

```bash
./upgrade.sh
```

## Related Documentation

- [Troubleshooting](TROUBLESHOOTING.md)
- [Custom Machinery Module](CUSTOM_MODULE.md)
