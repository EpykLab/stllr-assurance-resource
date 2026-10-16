# Stellarbridge assurance resources

Reusable assurance content and tools for moving that content into other systems.

```text
resources/
  fedramp/20x/class-a/linear/   FedRAMP Class A template, preview, and provenance
  soc2/                       Future SOC 2 resources
  cmmc/                       Future CMMC resources
  schemas/                    Future shared JSON Schemas
tools/
  linear-template/            Linear importer, dependencies, tests, and packaging
dist/
  linear-fedramp-class-a.zip   Self-contained package for recipients
```

The current resource is the [FedRAMP 20x Class A Linear template](resources/fedramp/20x/class-a/linear/README.md): seven milestones and 51 issues, including 43 sub-issues. SOC 2, CMMC, and schema directories reserve locations for future content.

## Use the Linear importer

Preview the bundled resource locally without installing dependencies:

```sh
python3 tools/linear-template/import_template.py preview
```

Follow the [importer instructions](tools/linear-template/README.md) to install its browser dependency and create a reusable template in another Linear organization. The `--file` flag selects a different compatible resource.

To distribute the current resource, send [the ZIP package](dist/linear-fedramp-class-a.zip). The ZIP includes recipient instructions and runs independently of this repository.

## Validate and package

```sh
python3 -m unittest discover -s tools/linear-template/tests -p "test_*.py" -v
python3 tools/linear-template/build_package.py
```

The build refreshes resource checksums and recreates the standalone ZIP with its own checksums. Browser dependencies, cached files, credentials, and import receipts are excluded.

## Add resources

Keep framework content under `resources/<framework>/`, with version or variant directories where needed. Put framework-specific schemas beside the resources they describe; use `resources/schemas/` for schemas shared across frameworks or tools.

Keep executable tools, dependencies, tests, and usage documentation together under `tools/<tool>/`. Put generated recipient bundles under `dist/`.

Code follows the GNU Affero General Public License, version 3 or later; see [LICENSE](LICENSE). Source-derived framework content retains its documented provenance.
