# Benji's own best practices

## Makefile

Practice: Use Makefile to centralize project commands
Logistics: A single Makefile at the root of the project, self-documenting. README should reference it and should NOT duplicate the command list.
When to use: Any filesystem-based project which has CLI executable commands specific to the project.
Principle: Source of authority
Examples: Can include wrappers for commands inside docker containers; frequently used lifecycle commands like build, test, deploy; references to project-specific shell scripts, wrappers for package manager commands like npm run.
Pointers: Use arguments to keep DRY and dependencies to chain commands together.

## Docker-based development, testing, and deployment

Practice: Use docker to create isolated environments for development, testing, and deployment
Logistics: A single docker-compose.yml at the project root, or (when multiple files are needed) within a docker/ subdirectory which will also contain Dockerfile's, scripts, config files, etc for created containers.
When to use: Any filesystem-based project which requires code execution or additional OS dependencies.
Principle: Dependency isolation
Pointers: Use multi-phase docker files to keep DRY and consistent between development, testing, and deployment images. Secrets should always be encrypted at rest.

## File audience isolation

Practice: Preserve re-usability while maintaining data privacy
Logistics: Keep files/directories structured to facilitate preservation in different remote locations appropriate for each audience.
Summary: Separate files by audience to facilitate sharing and backup.
- reusable source code which would be useful to others (e.g. public github repo)
- instance-specific configuration (mounted into app container) (e.g. personal/organizational backup, changes infrequently, typically only needed for disaster recovery)
- instance specific data (mounted) (e.g. personal/organizational backup, changes frequently)
