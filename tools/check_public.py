"""Check that nothing private gets published.

    python tools/check_public.py           # tracked files (CI)
    python tools/check_public.py --staged  # staged files, plus quotes from the private ledger (pre-commit)

Fails when a tracked or staged file
- lies under ledger/ (the private ledgers),
- is YAML or JSON with quote, quote_prefix or quote_suffix fields,
- contains an email address other than a noreply address,
- (--staged only) contains a quote, prefix or suffix from ledger/*.yaml, compared after normalization n1.
Findings name the file and record, never the quoted text.
"""
import glob
import json
import re
import subprocess
import sys
import unicodedata

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ALLOWED_EMAIL = re.compile(r"(@users\.noreply\.github\.com|^noreply@anthropic\.com)$")
QUOTE_KEYS = {"quote", "quote_prefix", "quote_suffix"}
QUOTE_FIELD = re.compile(r"""(?<![\w-])["']?(quote|quote_prefix|quote_suffix)["']?\s*:""")
MIN_QUOTE_CHARS = 20  # normalized length; shorter text would match by chance


def normalize(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    return "".join(ch for ch in text if ch.isalnum())


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout


def files(staged):
    if staged:
        names = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    else:
        names = git("ls-files", "-z")
    return [n for n in names.decode("utf-8").split("\0") if n]


def content(path, staged):
    raw = git("show", f":{path}") if staged else open(path, "rb").read()
    return raw.decode("utf-8", errors="ignore")


def has_quote_keys(node):
    if isinstance(node, dict):
        return any(k in QUOTE_KEYS or has_quote_keys(v) for k, v in node.items())
    if isinstance(node, list):
        return any(has_quote_keys(v) for v in node)
    return False


def has_quote_fields(text):
    # Parse so that compact JSON and flow-style YAML are caught; fall back to a
    # pattern when the file does not parse.
    import yaml

    try:
        docs = list(yaml.safe_load_all(text))
    except yaml.YAMLError:
        return bool(QUOTE_FIELD.search(text))
    return any(has_quote_keys(d) for d in docs)


def ledger_quotes():
    import yaml

    quotes = []
    for path in sorted(glob.glob("ledger/*.yaml") + glob.glob("ledger/*.jsonl")):
        with open(path, encoding="utf-8") as f:
            if path.endswith(".jsonl"):
                records = [json.loads(line) for line in f if line.strip()]
            else:
                records = yaml.safe_load(f) or []
            if isinstance(records, dict):  # {"ledger": header, "records": [...]}
                records = records.get("records") or []
            for rec in records:
                if "ledger" in rec:  # JSON Lines header line
                    continue
                for field in ("quote", "quote_prefix", "quote_suffix"):
                    norm = normalize(rec.get(field) or "")
                    if len(norm) >= MIN_QUOTE_CHARS:
                        quotes.append((f"{path} {rec.get('id')} {field}", norm))
    return quotes


def main():
    staged = "--staged" in sys.argv[1:]
    quotes = ledger_quotes() if staged else []
    problems = []
    for path in files(staged):
        if path.replace("\\", "/").startswith("ledger/"):
            problems.append(f"{path}: private ledger file")
            continue
        text = content(path, staged)
        is_data = path.endswith((".yaml", ".yml", ".json", ".jsonl")) and not path.endswith(".schema.json")
        if is_data and has_quote_fields(text):
            problems.append(f"{path}: has quote fields; publish only masked or locator exports")
        for email in sorted(set(EMAIL.findall(text))):
            if not ALLOWED_EMAIL.search(email):
                problems.append(f"{path}: contains an email address that is not a noreply address")
                break
        if quotes:
            norm = normalize(text)
            for where, quote in quotes:
                if quote in norm:
                    problems.append(f"{path}: contains source text from {where}")
    for p in problems:
        print(p, file=sys.stderr)
    if problems:
        print(f"check_public: {len(problems)} problem(s); nothing private may be published", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
