# Releasing Verisim

Verisim publishes to PyPI from GitHub Actions with PyPI Trusted Publishing.
No long-lived PyPI token is stored in GitHub.

## One-Time Setup

1. Create or sign in to your PyPI account.
2. Verify your PyPI email address and enable two-factor authentication.
3. In PyPI, open **Account settings** > **Publishing**.
4. Add a pending GitHub publisher with these exact values:

   ```text
   PyPI project name: verisim
   Owner: Harshal96
   Repository name: verisim
   Workflow filename: release.yml
   Environment name: pypi
   ```

5. In GitHub, open **Harshal96/verisim** > **Settings** > **Environments**.
6. Create an environment named `pypi`.
7. Recommended: add required reviewers to the `pypi` environment so each PyPI
   publish needs an explicit approval in GitHub Actions.

The PyPI pending publisher does not reserve the `verisim` name. Publish the
first release soon after configuring it.

## Release Process

1. Make sure `pyproject.toml` has the version you want to publish.
2. Run the local checks:

   ```bash
   uv sync --extra dev
   uv run pytest
   uv build --no-sources
   uv run --with twine python -m twine check dist/*
   ```

3. Commit and push the release changes to `main`.
4. Create and push a tag that matches the project version. Pushing the tag
   starts the `Release` workflow and publishes to PyPI through the `pypi`
   environment:

   ```bash
   git tag -a v0.1.0 -m "Release v0.1.0"
   git push origin main
   git push origin v0.1.0
   ```

5. If the `pypi` GitHub environment requires approval, approve the deployment.
6. Wait for the `Release` workflow to finish.
7. Verify the package at <https://pypi.org/project/verisim/>.
8. Optional: create a GitHub Release for the tag after PyPI publish succeeds.

## Troubleshooting

- If PyPI says the trusted publisher is invalid, re-check the owner,
  repository, workflow filename, and environment name exactly.
- If the workflow says the release tag does not match, use `v<version>`, where
  `<version>` is the value in `pyproject.toml`.
- If PyPI says the file already exists, bump the version in `pyproject.toml`.
  PyPI does not allow replacing an uploaded distribution file.
