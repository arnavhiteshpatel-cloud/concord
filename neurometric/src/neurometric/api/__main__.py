"""Command line: ``python -m neurometric.api <command>``.

Commands
--------
serve          run the API (uvicorn) over a study database
seed-demo      create the SYNTHETIC demo study ("DEMO - synthetic data, not patients")
create-admin   bootstrap an organization and its first admin (password from
               NEUROMETRIC_ADMIN_PASSWORD or an interactive prompt)
backup         online backup + manifest;  verify-backup / restore
verify-audit   recompute the audit hash chain
gen-key        print a new NEUROMETRIC_REID_KEY value
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m neurometric.api", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--db", required=True)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    d = sub.add_parser("seed-demo")
    d.add_argument("--db", required=True)
    d.add_argument("--per-modality", type=int, default=2)
    d.add_argument("--seed", type=int, default=7)
    c = sub.add_parser("create-admin")
    c.add_argument("--db", required=True)
    c.add_argument("--org", required=True)
    c.add_argument("--username", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--db", required=True)
    b.add_argument("--out", required=True)
    vb = sub.add_parser("verify-backup")
    vb.add_argument("path")
    rs = sub.add_parser("restore")
    rs.add_argument("backup")
    rs.add_argument("target")
    va = sub.add_parser("verify-audit")
    va.add_argument("--db", required=True)
    va.add_argument("--expected-head")
    sub.add_parser("gen-key")
    args = ap.parse_args(argv)

    if args.cmd == "gen-key":
        from ..study.security import generate_field_key
        print(generate_field_key())
        return 0
    if args.cmd == "serve":
        import uvicorn
        from .app import create_app
        uvicorn.run(create_app(args.db), host=args.host, port=args.port, server_header=False)
        return 0
    if args.cmd in ("verify-backup", "restore"):
        from ..study.backup import restore_database, verify_backup
        out = verify_backup(args.path) if args.cmd == "verify-backup" else restore_database(
            args.backup, args.target)
        print(json.dumps(out, indent=2))
        return 0 if out.get("ok", True) else 1
    from ..study import StudyService
    from ..study.audit import SYSTEM
    svc = StudyService(args.db)
    if args.cmd == "seed-demo":
        from ..study.demo import seed_demo
        res = seed_demo(svc, n_per_modality=args.per_modality, seed=args.seed)
        print("Created SYNTHETIC demo study:", res["study_title"])
        print("Study id:", res["study_id"])
        for role, user in res["users"].items():
            print(f"  {role:16s} {user}")
        if not os.environ.get("NEUROMETRIC_DEMO_PASSWORD"):
            print("Demo password (shown once):", res["password"])
        print(res["note"])
        return 0
    if args.cmd == "create-admin":
        pw = os.environ.get("NEUROMETRIC_ADMIN_PASSWORD") or getpass.getpass("Admin password: ")
        org = svc.create_organization(args.org)
        u = svc.create_user(SYSTEM, org_id=org["id"], username=args.username, password=pw,
                            role="admin", display_name=args.username)
        print(json.dumps({"organization_id": org["id"], "admin_user_id": u["id"]}))
        return 0
    if args.cmd == "backup":
        from ..study.backup import backup_database
        print(json.dumps(backup_database(svc.db, args.out), indent=2))
        return 0
    if args.cmd == "verify-audit":
        out = svc.audit.verify_chain(args.expected_head)
        print(json.dumps(out, indent=2))
        return 0 if out["ok"] else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
