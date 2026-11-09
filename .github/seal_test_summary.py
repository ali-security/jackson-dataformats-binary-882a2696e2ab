"""Print a per-suite and total summary of the surefire reports, naming every
skipped test with its reason.

The Maven runs use `-q` (GitHub) or only print per-class counts (Travis), so
this script makes the passing-test count and each skip reason explicit in the
CI log. JUnit 4 `Assume.assumeTrue(cond)` without a message reports only the
Hamcrest text "got: <false>, expected: is <true>"; for those skips the upstream
source comment that documents the assumption is printed alongside it.
"""
import glob
import os
import re
import xml.etree.ElementTree as ET

BARE = re.compile(r"^\s*(got: <false>, expected: is <true>)?\s*$", re.S)


def _source(classname):
    rel = classname.replace(".", "/") + ".java"
    hits = glob.glob(os.path.join("*", "src", "test", "java", rel))
    if not hits:
        return None, []
    with open(hits[0], encoding="utf-8", errors="replace") as fh:
        return hits[0], [l.rstrip("\r\n") for l in fh]


def _method_body(lines, start):
    body = []
    for i in range(start, len(lines)):
        if i > start and re.match(r"^    (@|public |private |protected |})", lines[i]):
            break
        body.append((i, lines[i]))
    return body


def _assume_comments(body):
    out = []
    for idx, (i, line) in enumerate(body):
        if "assume" in line.lower() and "(" in line:
            comments = []
            j = idx - 1
            while j >= 0 and body[j][1].strip().startswith("//"):
                comments.insert(0, body[j][1].strip().lstrip("/").strip())
                j -= 1
            out.append((i + 1, " ".join(comments) or line.strip()))
    return out


def explain(classname, testname):
    path, lines = _source(classname)
    if not lines:
        return None
    name = testname.split("[")[0]
    found = []
    for i, line in enumerate(lines):
        if re.search(r"\bvoid\s+%s\s*\(" % re.escape(name), line):
            found = _assume_comments(_method_body(lines, i))
            break
    if not found:
        for i, line in enumerate(lines):
            if line.strip() == "@Before":
                found = _assume_comments(_method_body(lines, i + 1))
                break
    if not found:
        return None
    return "; ".join("%s:%d: %s" % (os.path.basename(path), n, c) for n, c in found)


def main():
    tot = [0, 0, 0, 0]
    skipped = []
    for f in sorted(glob.glob("*/target/surefire-reports/TEST-*.xml")):
        r = ET.parse(f).getroot()
        t, fl, e, sk = (int(r.get(k, 0)) for k in ("tests", "failures", "errors", "skipped"))
        tot = [a + b for a, b in zip(tot, (t, fl, e, sk))]
        print("SUITE %s: Tests run: %d, Failures: %d, Errors: %d, Skipped: %d" % (r.get("name"), t, fl, e, sk))
        for tc in r.iter("testcase"):
            s = tc.find("skipped")
            if s is None:
                continue
            msg = (s.get("message") or s.text or "").strip()
            line = "SKIPPED %s.%s -- reason: %s" % (tc.get("classname"), tc.get("name"), msg or "(no message)")
            if BARE.match(msg):
                why = explain(tc.get("classname"), tc.get("name"))
                if why:
                    line += " -- upstream assumption comment: " + why
            print("  " + line)
            skipped.append(line)
    print("TEST SUMMARY: Tests run: %d, Passed: %d, Failures: %d, Errors: %d, Skipped: %d"
          % (tot[0], tot[0] - tot[1] - tot[2] - tot[3], tot[1], tot[2], tot[3]))
    if skipped:
        print("SKIPPED TESTS AND REASONS (%d):" % len(skipped))
        for line in skipped:
            print("  " + line)


if __name__ == "__main__":
    main()
