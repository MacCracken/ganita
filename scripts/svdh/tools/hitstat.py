#!/usr/bin/env python3
"""hitstat.py [DIR|FILE.json ...] [--select REASON --out FILE.json]: counts of hunt hits
(adv/hunt.py's format), per tree, and per family (the first word of the label) and set of
reasons (the words of each `why` entry before its first number: nw, uo, vo, rec, nonfinite S,
not desc, status, driver exit, driver output).  A DIR stands for DIR/*.json; the default is
$SVDH_WORK/hunt_hits (default <repo>/build/svdh/hunt_hits), where hunt.py and hunt_all.sh write.
Hits are counted once per label, as hunt.py keeps them.
--select REASON --out FILE.json also writes the hits with that reason to FILE.json, in the same
format, for hunts/mkwit.py to give them an exact oracle.
Exits with status 2 on a usage or input error (a missing or malformed hit file, as
corpus.read_hits checks it, an unwritable FILE.json), and 1 when no hit has the --select reason
(nothing is written then).
"""
import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import corpus as C   # noqa: E402


def kind(why):
    """'nw 35' and 'nw inf' -> 'nw'; 'status -3 / vo -3' -> 'status'; 'nonfinite S' -> 'nonfinite S'."""
    words = []
    for w in why.split():
        if re.match(r'^[-+]?([0-9]|inf|nan)', w):
            break
        words.append(w)
    return ' '.join(words) or why


def main():
    ap = argparse.ArgumentParser(description='Counts of hunt hits per tree, family and reason.')
    ap.add_argument('paths', nargs='*', metavar='DIR|FILE.json',
                    help='hit files, or directories of them (default $SVDH_WORK/hunt_hits)')
    ap.add_argument('--select', metavar='REASON', help="with --out: the hits with this reason, e.g. 'nonfinite S'")
    ap.add_argument('--out', metavar='FILE.json', help='with --select: where to write them')
    a = ap.parse_args()
    if (a.select is None) != (a.out is None):
        ap.error('--select and --out go together')
    args = a.paths or [os.path.join(C.WORK, 'hunt_hits')]
    paths = []
    for p in args:
        if os.path.isdir(p):
            paths += sorted(glob.glob(os.path.join(p, '*.json')))
        elif os.path.isfile(p):
            paths.append(p)
        else:
            C.input_error('hitstat.py: %s is neither a directory nor a file' % p)
    if not paths:
        C.input_error('hitstat.py: no hit files (*.json) in %s' % ' '.join(args))
    seen = set()
    trees, groups = {}, {}
    picked = []
    for p in paths:
        try:
            hits = C.read_hits(p)             # a ValueError, with a message, on a malformed file
        except ValueError as e:
            C.input_error('hitstat.py: %s' % e)
        for h in hits:
            if h['label'] in seen:
                continue
            seen.add(h['label'])
            tree = h.get('tree', '?')
            trees[tree] = trees.get(tree, 0) + 1
            kinds = [kind(w) for w in h.get('why', [])]
            key = (h['label'].split()[0], ' + '.join(kinds) or '-')
            groups[key] = groups.get(key, 0) + 1
            if a.select is not None and a.select in kinds:
                picked.append(h)
    print('hits: %d in %d files; per tree: %s' % (len(seen), len(paths),
                                                  ', '.join('%s %d' % kv for kv in sorted(trees.items()))))
    print('per family and reasons:')
    for (fam, why), n in sorted(groups.items(), key=lambda t: (-t[1], t[0])):
        print('  %8d  %-8s %s' % (n, fam, why))
    if a.out is not None:
        if not picked:
            sys.exit('hitstat.py: no hit has the reason %r; %s not written' % (a.select, a.out))
        try:
            with open(a.out, 'w') as fh:
                json.dump(picked, fh)
        except OSError as e:
            C.input_error('hitstat.py: cannot write %s: %s' % (a.out, e.strerror))
        print('wrote %d hits with the reason %r to %s' % (len(picked), a.select, a.out))


if __name__ == '__main__':
    main()
