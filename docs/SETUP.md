# Initial Setup

This guide explains how to set up this forked Weblate docker-compose repository.

## 1. Clone Your Fork

```bash
git clone git@github.com:Muso-AI/weblate-docker-compose.git
cd weblate-docker-compose
```

## 2. Configure Upstream Remote (One-time Setup)

The upstream remote should already be configured. Verify it exists:

```bash
git remote -v
```

You should see:
- `origin` - Your fork (Muso-AI/weblate-docker-compose)
- `upstream` - Original repository (WeblateOrg/docker-compose)

If the upstream remote is missing, add it:

```bash
git remote add upstream https://github.com/WeblateOrg/docker-compose.git
```

## 3. Create Configuration Files

Create your `docker-compose.override.yml` file based on the example:

```bash
cp docker-compose.override.yml.example docker-compose.override.yml
```

Edit `docker-compose.override.yml` with your settings. The example includes:
- Custom machinery module mounting
- Environment variables for email, admin, and domain configuration
- Port mappings

**Important**: The override file includes the volume mount for your custom machinery module:
```yaml
volumes:
  - ./machinery_custom:/app/data/python/machinery_custom
```

And the environment variable to enable it:
```yaml
WEBLATE_MACHINERY: weblate.machinery.weblatememory.WeblateMemory,machinery_custom.CustomGoogleV3Advanced
WEBLATE_ADD_MACHINERY: machinery_custom.CustomGoogleV3Advanced
```

## 4. Configure Weblate

admin credentials:
- login: admin
- password: admin

- You need to setup SSH key to access the git repository.
- You need to setup automatic suggestion service, in our case we use Custom Google V3 Advanced. Setup the same as for 
https://docs.weblate.org/en/weblate-5.15.2/admin/machine.html#mt-google-translate-api-v3

- You need to create a new project or restore project from backup.

