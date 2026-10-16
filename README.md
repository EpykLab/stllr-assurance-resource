# FedRAMP 20x Class A portable Linear template

Share this entire folder or its ZIP with the recipient. It contains the saved project's reusable template content and a browser importer that creates a **native Linear project template** in the recipient's organization.

The recipient signs in to their own Linear account in a browser opened on their computer. No source organization access, API key, Weave installation, or paid external service is needed. The resulting template is workspace-level, with projects and issues assigned to the destination team they select.

## What is included

- Seven milestones, with descriptions and exit criteria.
- 51 issues: eight parent issues and 43 sub-issues.
- The three checklists: 23 mandatory, 11 recommended, and nine optional rules.
- All milestone assignments, 209 completion checkboxes, one response-target table, and public FedRAMP source links.

The export was captured from the saved template on October 16, 2026. Organization IDs, source issue identifiers, assignees, cycles, fixed dates, and the source Compliance initiative are excluded. Internal Linear links and local fragment links are converted to text references. Comments, history, issue relationship edges other than parent/sub-issue relationships, and documents from the original project are outside this template export. All issues use No priority.

Review the current FedRAMP rules and Class A applicability before using this work plan. Completing the work plan does not establish that certification has been awarded.

## 1. Inspect the package

Install Python 3.10 or later. Extract the ZIP and open a terminal in the `linear-fedramp-class-a` folder.

Run this before installing any browser dependency:

```sh
python3 import_template.py preview
```

This validates the file and prints the milestone and issue counts. It runs locally, opens no browser, and changes no Linear data. `template.json` is the portable export; `CONTENTS.html` is a local, read-only view of its complete content. The JSON is a custom package for this importer, not a file accepted by Linear's built-in CSV importer.

## 2. Install the browser importer

On macOS or Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
```

On Windows, use PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

For the commands below, Windows users can replace `python` with `.\.venv\Scripts\python.exe`.

On Linux, Chromium may need system libraries. Follow the [Playwright installation instructions](https://playwright.dev/python/docs/intro) if the browser reports missing dependencies.

## 3. Choose the destination

Find these values in the recipient's own Linear organization:

- **Workspace slug:** for `https://linear.app/acme/...`, use `acme`.
- **Team key:** the prefix of that team's issue identifiers. For `SEC-123`, use `SEC`.
- **Statuses:** the exact project and issue status names to pre-fill. Both default to `Backlog`. Use `--project-status` and `--issue-status` if the destination uses different names.

The signed-in account must be able to manage workspace project templates and access the selected team. Workspace administrators may restrict these permissions.

Preview the destination mapping, replacing the examples with real values:

```sh
python import_template.py import --workspace acme --team SEC
```

This is still a local preview. Add `--json` for machine-readable output.

## 4. Create the template

```sh
python import_template.py import --workspace acme --team SEC --apply
```

A Chromium window opens. Sign in to the destination organization there; the importer waits up to 15 minutes. Complete any SSO, MFA, or passkey steps yourself. Do not close or interact with the browser after the importer starts filling the template.

The importer checks for an existing template with the same name, fills a new draft, checks counts and rich-text content, then clicks Create once. It reopens the saved template and verifies all 51 issue rows and parent relationships. It creates the reusable template only; no live project or live issues are instantiated.

On success, the terminal prints the new template URL. The `import-result` folder contains:

- `receipt.json`: destination, package fingerprint, counts, verification time, and template URL.
- `imported-template.png`: a screenshot of the saved template.

Authentication uses an isolated, non-persistent browser context that closes afterward. The importer does not export cookies, save an authentication profile, or request an API key. Rich-text pastes use the local system clipboard and may replace its previous contents.

For different destination status names:

```sh
python import_template.py import --workspace acme --team SEC \
  --project-status Planned --issue-status Todo --apply
```

For a separate template copy:

```sh
python import_template.py import --workspace acme --team SEC \
  --name "Class A certification starter" --output-dir second-import --apply
```

`--name` changes the template's display name. The default project title remains `project.name` from the JSON and can be changed when creating a project.

## 5. Use it in Linear

Open the destination's **Settings → Projects → Templates** and check the imported template. When creating a new project, select this template and the destination team. Set project and milestone dates, assign owners, and review applicable rule dispositions for that offering.

Linear documents this creation flow in [Project templates](https://linear.app/docs/project-templates).

## Troubleshooting and retrying

- **An existing template name is found:** the importer stops without overwriting it. Open it to see whether a previous attempt succeeded, or use a new `--name` for a deliberate separate copy.
- **A receipt already exists:** check its URL before retrying. Use a new name and output directory only when creating a separate copy.
- **The team or status cannot be found:** verify the workspace slug, team key, exact status names, and account access. The importer stops before the final Create action.
- **The UI changes or rich-text verification fails:** the importer stops and writes `import-result/import-error.png` when possible. Before final submission, the template is only a browser draft and is discarded when the browser closes. No existing template is edited.
- **An error or interruption occurs after Create was attempted:** check the destination template list before running again. A lost response can still mean creation succeeded. The importer deliberately does not retry final submission or delete anything.
- **The script times out at login:** restart it and complete sign-in within 15 minutes. If login lands elsewhere, navigate the opened browser to `https://linear.app/YOUR-WORKSPACE/settings/project-templates`.
- **An operating-system clipboard policy prevents rich-text paste:** use a machine/session that permits clipboard access for the importer. It stops before creation if the expected text, table, or checkbox count is missing.

## Validation and limitations

The export was read from the saved template, not reconstructed from shortened issue summaries. Offline tests cover the complete graph, counts, source-ID removal, HTML safety, destination inputs, and preview behavior. A browser check confirmed that the exported response-target issue pastes with complete text, five checkboxes, its table, and three public links; that test draft was discarded.

The importer follows Linear's template editor observed on October 16, 2026. It does not rely on the undocumented nested structure of the API's `templateData` JSON. A full import into a second organization has not been run here; that requires the recipient's account and destination permissions. Future Linear UI changes may require selector updates. Failures stop before the final Create action where possible; a post-submission failure can leave a saved template.

Run the offline checks:

```sh
python -m unittest discover -s . -p "test_*.py" -v
```

To customize the content, edit `template.json` and run preview again. Keep keys unique, preserve milestone and parent references, and use only one sub-issue level. The importer validates the supported version-1 fields before opening a browser.

## Files

| File | Purpose |
| --- | --- |
| `template.json` | Portable, editable content export |
| `CONTENTS.html` | Complete local content preview without scripts |
| `import_template.py` | Preview, validate, and import commands |
| `requirements.txt` | Pinned Playwright dependency |
| `test_import_template.py` | Offline validation tests |
| `SHA256SUMS` | File checksums for the distributed package |

The importer code follows the repository's GNU Affero General Public License, version 3 or later, in `LICENSE`. The FedRAMP links and source-derived rule descriptions retain their original provenance.
