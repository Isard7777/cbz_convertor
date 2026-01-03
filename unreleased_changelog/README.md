# Changelog Fragments

This directory contains changelog fragments that will be automatically compiled into `CHANGELOG.md` during a release.

## Creating fragments

Fragments are simple markdown files placed directly in this directory (`unreleased_changelog/`).

### File naming format

Fragments must follow this format:

```
<number>.<type>.md
```

Where:
- `<number>` : Any unique identifier (issue/PR number, date, etc.)
- `<type>` : One of: `feature` or `fix`
- `.md` : File extension

### Examples

```bash
# For features
001.feature.md
fix-memory-leak.feature.md
issue-123.feature.md

# For bugfixes
002.fix.md
crash-fix.fix.md
issue-124.fix.md
```

### Fragment content

The file should contain a **single line** describing the change:

```
echo "Added support for WebP image format" > 001.feature.md
```

Or:

```
echo "Fixed crash when processing corrupted metadata" > 002.fix.md
```

## During release

When preparing a release, run:

```bash
towncrier build --version 0.2.0
```

This will:
1. Read all fragments from this directory
2. Add them to `CHANGELOG.md` under the new version
3. Delete the fragment files
4. Create a backup: `CHANGELOG.md.bak`

## Examples

### Add a feature

```bash
echo "Sequential image renaming with zero-padding" > 001.feature.md
```

### Add a bugfix

```bash
echo "Fixed issue with special characters in filenames" > 002.fix.md
```

## Best practices

- Keep descriptions short (one line)
- Use past tense: "Added", "Fixed", "Improved"
- Start with a capital letter
- One fragment per change
- Commit fragments with their code changes

## See also

- [VERSIONING.md](../VERSIONING.md) - Version management guide
- [CHANGELOG.md](../CHANGELOG.md) - Release history

