#!/usr/bin/env python3
"""Preview or import a portable project template through Linear's browser editor."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse


VERSION = "1.0.0"
DEFAULT_PACKAGE = Path(__file__).with_name("template.json")
FORMAT = "linear-project-template-portable"
KEY = re.compile(r"[A-Za-z0-9_-]+\Z")


class PackageError(ValueError):
    pass


class ContentValidator(HTMLParser):
    tags = {
        "p", "h1", "h2", "h3", "h4", "ul", "ol", "li", "strong", "em",
        "code", "pre", "blockquote", "br", "table", "tbody", "thead", "tr",
        "td", "th", "a",
    }

    def handle_starttag(self, tag, attrs):
        if tag not in self.tags:
            raise PackageError(f"Unsupported HTML element: {tag}")
        for name, value in attrs:
            if tag == "a" and name == "href":
                url = urlparse(value or "")
                if url.scheme != "https" or not url.netloc or url.username or url.password:
                    raise PackageError("Description links must use HTTPS without credentials")
                if url.hostname and (url.hostname == "linear.app" or url.hostname.endswith(".linear.app")):
                    raise PackageError("Remove organization-specific Linear links before importing")
            elif name == "data-type" and value in {"todo_list", "todo_item"}:
                pass
            elif name == "data-done" and value == "false":
                pass
            else:
                raise PackageError(f"Unsupported HTML attribute: {tag}.{name}")

    def handle_endtag(self, tag):
        if tag not in self.tags:
            raise PackageError(f"Unsupported HTML closing element: {tag}")

    def handle_comment(self, data):
        raise PackageError("HTML comments are not supported")


class ContentText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, value):
        self.parts.append(value)

    def handle_starttag(self, tag, attrs):
        if tag not in {"a", "strong", "em", "code"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        self.handle_starttag(tag, [])


def normalized_text(value):
    return " ".join(value.split())


def html_text(value):
    reader = ContentText()
    reader.feed(value)
    return normalized_text("".join(reader.parts))


def text(value, location, allow_empty=False):
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise PackageError(f"{location} must be {'a string' if allow_empty else 'a nonempty string'}")
    return value


def fields(obj, required, optional, location):
    if not isinstance(obj, dict):
        raise PackageError(f"{location} must be an object")
    missing = set(required) - obj.keys()
    unknown = obj.keys() - set(required) - set(optional)
    if missing or unknown:
        raise PackageError(f"{location}: missing fields {sorted(missing)}; unsupported fields {sorted(unknown)}")


def validate_package(data):
    fields(data, {"format", "version", "name", "project", "milestones", "issues"},
           {"exported_on", "notes"}, "package")
    if data["format"] != FORMAT or type(data["version"]) is not int or data["version"] != 1:
        raise PackageError("Unsupported package format/version; expected portable version 1")
    text(data["name"], "name")
    fields(data["project"], {"name", "summary", "description"}, set(), "project")
    for key, value in data["project"].items():
        text(value, f"project.{key}", allow_empty=key != "name")
    milestones, issues = data["milestones"], data["issues"]
    for label, values in (("milestones", milestones), ("issues", issues)):
        if not isinstance(values, list) or not 1 <= len(values) <= 1000:
            raise PackageError(f"{label} must contain 1–1000 entries")
    known = {}
    for label, values, required in (
        ("milestones", milestones, {"key", "name", "description"}),
        ("issues", issues, {"key", "title", "description_html", "milestone", "parent", "priority"}),
    ):
        keys, titles = set(), set()
        for index, value in enumerate(values):
            at = f"{label}[{index}]"
            fields(value, required, set(), at)
            key = text(value["key"], f"{at}.key")
            if not KEY.fullmatch(key) or key in keys:
                raise PackageError(f"{at}: invalid or duplicate key {key!r}")
            keys.add(key)
            title = text(value.get("name", value.get("title")), f"{at}.name/title")
            if title in titles:
                raise PackageError(f"{at}: duplicate name/title {title!r}")
            titles.add(title)
            if label == "issues":
                text(value["description_html"], f"{at}.description_html", allow_empty=True)
                ContentValidator().feed(value["description_html"])
                if type(value["priority"]) is not int or value["priority"] != 0:
                    raise PackageError("Version 1 imports issues with no priority; expected priority 0")
            else:
                text(value["description"], f"{at}.description", allow_empty=True)
        known[label] = keys
    by_key = {issue["key"]: issue for issue in issues}
    for issue in issues:
        if not isinstance(issue["milestone"], str) or issue["milestone"] not in known["milestones"]:
            raise PackageError(f"{issue['key']}: unknown milestone")
        parent = issue["parent"]
        if parent is not None:
            if not isinstance(parent, str) or parent not in by_key or parent == issue["key"]:
                raise PackageError(f"{issue['key']}: invalid parent")
            if by_key[parent]["parent"] is not None:
                raise PackageError(f"{issue['key']}: version 1 supports one level of sub-issues")
    return data


def load_package(path):
    if path.stat().st_size > 2_000_000:
        raise PackageError("Package exceeds the 2 MB limit")
    return validate_package(json.loads(path.read_text(encoding="utf-8")))


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def ordered_issues(data):
    children = {}
    for issue in data["issues"]:
        children.setdefault(issue["parent"], []).append(issue)
    for root in children.get(None, []):
        yield root
        yield from children.get(root["key"], [])


def plan(data, args):
    counts = Counter(issue["milestone"] for issue in data["issues"])
    return {
        "name": args.name or data["name"], "package_sha256": fingerprint(data),
        "workspace": args.workspace, "team": args.team,
        "scope": "workspace", "project_status": args.project_status,
        "issue_status": args.issue_status, "issues": len(data["issues"]),
        "parent_issues": sum(i["parent"] is None for i in data["issues"]),
        "sub_issues": sum(i["parent"] is not None for i in data["issues"]),
        "milestones": [dict(name=m["name"], issues=counts[m["key"]]) for m in data["milestones"]],
        "mode": "apply" if getattr(args, "apply", False) else "preview",
    }


def show_plan(value, as_json):
    if as_json:
        print(json.dumps(value, indent=2, ensure_ascii=False))
        return
    print(f"Template: {value['name']}")
    print(f"{len(value['milestones'])} milestones; {value['issues']} issues "
          f"({value['parent_issues']} parent issues, {value['sub_issues']} sub-issues)")
    if value["workspace"]:
        print(f"Destination: {value['workspace']} / {value['team']} (workspace template)")
    print(f"Project status: {value['project_status']}; issue status: {value['issue_status']}")
    for m in value["milestones"]:
        print(f"  {m['name']} — {m['issues']} issues")
    print(f"Package SHA-256: {value['package_sha256']}")
    if value["mode"] == "preview":
        print("Preview only. No browser opened and no Linear data changed.")


class LinearEditor:
    def __init__(self, page, context, expect, timeout_error):
        self.page, self.context = page, context
        self.expect, self.timeout_error = expect, timeout_error
        self.mod = "Meta" if sys.platform == "darwin" else "Control"

    def button(self, name):
        return self.page.get_by_role("button", name=name, exact=True)

    def textbox(self, name):
        return self.page.get_by_role("textbox", name=name, exact=True)

    def option(self, name):
        return self.page.get_by_role("option", name=name, exact=True)

    def choose(self, button, option):
        button.click()
        self.option(option).click()
        self.expect(self.page.get_by_role("dialog", name="Menu", exact=True)).to_have_count(0)

    def choose_team(self, button, key):
        button.click()
        options = self.page.get_by_role("option", name=re.compile(r"(?:^|\s)" + re.escape(key) + r"\s*$"))
        self.expect(options).to_have_count(1)
        options.click()
        self.expect(self.page.get_by_role("dialog", name="Menu", exact=True)).to_have_count(0)

    def finish_editor(self, field, save=False):
        if save:
            self.textbox(field).press(f"{self.mod}+Enter")
        else:
            self.button("Discard changes").click()
        try:
            self.expect(self.textbox(field)).to_have_count(0, timeout=2500)
        except (AssertionError, self.timeout_error):
            # A rich-text blur can replace the form before a pointer click lands.
            if save:
                self.textbox(field).press(f"{self.mod}+Enter")
            else:
                self.button("Discard changes").click()
            self.expect(self.textbox(field)).to_have_count(0)

    def paste_html(self, html):
        editor = self.textbox("Issue description")
        editor.click()
        self.page.evaluate("""async html => {
            await navigator.clipboard.write([new ClipboardItem({
                'text/html': new Blob([html], {type: 'text/html'}),
                'text/plain': new Blob([''], {type: 'text/plain'})
            })]);
        }""", html)
        editor.press(f"{self.mod}+v")
        if html:
            self.expect(editor).to_contain_text(re.compile(re.escape(html_text(html)).replace(r"\ ", r"\s+")))
            actual = normalized_text(editor.inner_text())
            if actual != html_text(html):
                raise PackageError("Pasted issue text differs from the export; stopping before template creation")
            expected_tasks = html.count('data-type="todo_item"')
            self.expect(editor.locator('[data-type="todo_item"]')).to_have_count(expected_tasks)
            self.expect(editor.locator("table")).to_have_count(html.count("<table>"))

    @staticmethod
    def row_name(issue, parent=None):
        title = issue["title"] + (" › " + parent["title"] if parent else "")
        return f"Backlog status. Change status {title} Move to milestone Set team Open sub-issue menu"

    def issue_row(self, issue, parent=None, status="Backlog"):
        name = self.row_name(issue, parent).replace("Backlog status.", status + " status.", 1)
        return self.button(name)

    def add_issue(self, issue, parent, milestones, team, status):
        if parent:
            self.issue_row(parent, status=status).get_by_role("button", name="Open sub-issue menu", exact=True).click()
            self.option("Add sub-issue").click()
        else:
            self.button("Add issue").last.click()
        self.textbox("Issue title").fill(issue["title"])
        self.paste_html(issue["description_html"])
        self.choose_team(self.button("Set team"), team)
        self.choose(self.page.get_by_role("button", name=re.compile(r"^Choose milestone\.")),
                    milestones[issue["milestone"]]["name"])
        status_button = self.page.get_by_role("button", name=re.compile(r"^Change status\."))
        if status_button.get_attribute("aria-label") != f"Change status. {status} is selected":
            self.choose(status_button, status)
        self.page.get_by_role("checkbox", name="Create more", exact=True).uncheck()
        self.finish_editor("Issue title", save=True)
        self.expect(self.issue_row(issue, parent, status)).to_have_count(1)

    def populate(self, data, args):
        self.button("Create new project template…").click()
        self.textbox("Name").fill(args.name or data["name"])
        self.textbox("Project name").fill(data["project"]["name"])
        self.textbox("Project summary").fill(data["project"]["summary"])
        self.textbox("Project description").fill(data["project"]["description"])
        self.choose_team(self.button("Change project teams"), args.team)
        self.choose(self.button("Change project status"), args.project_status)
        # The first milestone control is an icon-only button called Add.
        self.button("Add").click()
        for index, milestone in enumerate(data["milestones"]):
            if index:
                self.button("Add milestone").click()
            self.textbox("Milestone name").fill(milestone["name"])
            self.textbox("Milestone description template").fill(milestone["description"])
            self.finish_editor("Milestone name", save=True)
            self.expect(self.button(f"Milestones {index + 1}")).to_have_count(1)
        milestones = {m["key"]: m for m in data["milestones"]}
        issues = {i["key"]: i for i in data["issues"]}
        for index, issue in enumerate(ordered_issues(data)):
            print(f"Adding issue {index + 1}/{len(issues)}: {issue['title']}", file=sys.stderr)
            self.add_issue(issue, issues.get(issue["parent"]), milestones, args.team, args.issue_status)
            self.expect(self.button(f"Issues {index + 1}")).to_have_count(1)
        self.expect(self.button(f"Milestones {len(milestones)}")).to_have_count(1)
        self.expect(self.button("Template visibility")).to_contain_text("Workspace")


def apply_import(data, args):
    if (args.output_dir / "receipt.json").exists():
        raise PackageError(f"{args.output_dir / 'receipt.json'} already exists. Check the saved import before retrying. "
                           "For a separate copy, use a new --name and --output-dir.")
    try:
        from playwright.sync_api import sync_playwright, expect, TimeoutError as PlaywrightTimeout
    except ImportError as exc:
        raise PackageError("Install browser dependencies: python -m pip install -r requirements.txt; "
                           "then python -m playwright install chromium") from exc
    listing = f"https://linear.app/{args.workspace}/settings/project-templates"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.grant_permissions(["clipboard-read", "clipboard-write"], origin="https://linear.app")
        page = context.new_page()
        page.set_default_timeout(20000)
        editor = LinearEditor(page, context, expect, PlaywrightTimeout)
        submitted = False
        try:
            print(f"Sign in to {args.workspace} in the opened browser. Waiting up to 15 minutes.", file=sys.stderr)
            page.goto(listing)
            editor.button("Create new project template…").wait_for(state="visible", timeout=900000)
            if urlparse(page.url).path != urlparse(listing).path:
                raise PackageError("Unexpected workspace page. Check --workspace and your Linear permissions.")
            name = args.name or data["name"]
            existing = page.get_by_role("link", name=name, exact=True)
            if existing.count():
                raise PackageError(f"Template {name!r} already exists. Use --name to create a separate template.")
            editor.populate(data, args)
            # No retry after submission: a lost response can still mean a successful create.
            submitted = True
            editor.button("Create").click()
            page.wait_for_url(listing)
            saved = page.get_by_role("link", name=name, exact=True)
            expect(saved).to_have_count(1)
            saved.click()
            expect(editor.textbox("Name")).to_have_value(name)
            expect(editor.button(f"Milestones {len(data['milestones'])}")).to_have_count(1)
            expect(editor.button(f"Issues {len(data['issues'])}")).to_have_count(1)
            by_key = {i["key"]: i for i in data["issues"]}
            for issue in data["issues"]:
                expect(editor.issue_row(issue, by_key.get(issue["parent"]), args.issue_status)).to_have_count(1)
            receipt = plan(data, args)
            receipt.update(url=page.url, verified_at=datetime.now(timezone.utc).isoformat(), importer_version=VERSION)
            page.screenshot(path=str(args.output_dir / "imported-template.png"), full_page=True)
            (args.output_dir / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
            return receipt
        except BaseException:
            try:
                page.screenshot(path=str(args.output_dir / "import-error.png"), full_page=True)
            except Exception:
                pass
            if submitted:
                print("Submission was attempted. Check Linear for the template before trying again. "
                      "The importer will not retry the create action.", file=sys.stderr)
            else:
                print("The final Create action was not attempted. The browser draft will be discarded.", file=sys.stderr)
            raise
        finally:
            context.close()
            browser.close()


def parser():
    root = argparse.ArgumentParser(description=__doc__, epilog="Start with: python import_template.py preview")
    root.add_argument("--version", action="version", version=VERSION)
    commands = root.add_subparsers(dest="command")
    for name in ("preview", "import"):
        sub = commands.add_parser(name, help="Inspect the package" if name == "preview" else "Create a reusable Linear project template")
        sub.add_argument("--file", type=Path, default=DEFAULT_PACKAGE, help="Portable JSON package (default: bundled template.json)")
        sub.add_argument("--workspace", help="Destination workspace URL slug, e.g. acme")
        sub.add_argument("--team", help="Destination team key, e.g. SEC")
        sub.add_argument("--name", help="Template display name; use a new name for a separate copy")
        sub.add_argument("--project-status", default="Backlog", help="Exact destination project status (default: Backlog)")
        sub.add_argument("--issue-status", default="Backlog", help="Exact destination issue status (default: Backlog)")
        sub.add_argument("--json", action="store_true", help="Print the plan or completed receipt as JSON")
        if name == "import":
            sub.add_argument("--apply", action="store_true", help="Open the browser and create the template; otherwise preview only")
            sub.add_argument("--output-dir", type=Path, default=Path("import-result"), help="Local receipt and screenshot directory")
    return root


def main(argv=None):
    cli = parser()
    args = cli.parse_args(argv)
    if args.command is None:
        cli.print_help()
        return 0
    try:
        if args.workspace and not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.workspace):
            raise PackageError("--workspace must be the URL slug only, e.g. acme")
        if args.team and not re.fullmatch(r"[A-Za-z0-9_-]+", args.team):
            raise PackageError("--team must be a team key, e.g. SEC")
        if args.name is not None:
            text(args.name, "--name")
        data = load_package(args.file)
        if args.command == "import" and args.apply:
            if not args.workspace or not args.team:
                raise PackageError("import --apply requires --workspace and --team")
            result = apply_import(data, args)
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(f"Created and verified: {result['url']}\nReceipt: {args.output_dir / 'receipt.json'}")
        else:
            show_plan(plan(data, args), args.json)
        return 0
    except KeyboardInterrupt:
        print("Import interrupted. Check Linear before retrying if submission had started.", file=sys.stderr)
        return 130
    except (PackageError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Browser import stopped: {exc}\nSee README.md troubleshooting and import-error.png.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
