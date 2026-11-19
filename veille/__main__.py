"""Ligne de commande.

    python -m veille tout        # collecte + fiches IA + site (ce que fait GitHub chaque jour)
    python -m veille collecter   # seulement la collecte
    python -m veille resumer     # seulement les fiches IA
    python -m veille site        # seulement le site (dossier site/)
"""
import argparse
import logging

from .core import charger_config


def main():
    p = argparse.ArgumentParser(prog="veille", description="Veille scientifique automatisée")
    p.add_argument("action", choices=["tout", "collecter", "resumer", "site"], nargs="?", default="tout")
    p.add_argument("--config", default=None, help="chemin vers config.yaml")
    p.add_argument("--inline", action="store_true", help="site en un seul fichier HTML (aperçu hors-ligne)")
    p.add_argument("-v", "--verbeux", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbeux else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    cfg = charger_config(args.config)

    from . import pipeline, resume_ia, site
    if args.action in ("tout", "collecter"):
        pipeline.collecter(cfg)
    if args.action in ("tout", "resumer"):
        resume_ia.resumer(cfg)
    if args.action in ("tout", "site"):
        site.construire(cfg, inline=args.inline)


if __name__ == "__main__":
    main()
