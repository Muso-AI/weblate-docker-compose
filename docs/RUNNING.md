# Running Weblate

This guide explains how to start, stop, and manage your Weblate instance.

## Start Services

```bash
docker compose up -d
```

This will start:
- PostgreSQL database
- Valkey (Redis) cache
- Weblate application

## View Logs

```bash
docker compose logs -f weblate
```

To view logs for all services:

```bash
docker compose logs -f
```

## Stop Services

```bash
docker compose down
```

This stops all services gracefully.

## Restart Services

```bash
docker compose restart
```

To restart a specific service:

```bash
docker compose restart weblate
```

## Access Weblate

Once started, access Weblate at:
- `http://localhost:80` (or the port you configured in `docker-compose.override.yml`)

Use the admin credentials you set in `docker-compose.override.yml`.

## Check Service Status

```bash
docker compose ps
```

This shows the status of all running services.

## Related Documentation

- [Initial Setup](SETUP.md)
- [Troubleshooting](TROUBLESHOOTING.md)
