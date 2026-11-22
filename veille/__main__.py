"""Ligne de commande.

    python -m veille tout        # collecte + fiches IA + site (ce que fait GitHub chaque jour)
    python -m veille collecter   # seulement la collecte
    python -m veille resumer     # seulement les fiches IA
    python -m veille audio       # seulement les MP3 des fiches (edge-tts, dossier audio/)
    python -m veille site        # seulement le site (dossier site/)
    python -m veille notifier    # notifications du matin (ntfy) ; --essai : affiche sans envoyer
    python -m veille tester-ia   # vérifie que chaque fournisseur IA répond (OpenRouter, Gemini, Mistral)
    python -m veille deja_collecte  # affiche fait=oui / fait=non (collecte du jour déjà faite ?)
    python -m veille reste_rattrapage  # affiche reste=N (articles sans fiche IA ; 0 si ia.rattrapage.auto: false)
"""
import argparse
import logging

from .core import charger_config


def main():
    p = argparse.ArgumentParser(prog="veille", description="Veille scientifique automatisée")
    p.add_argument("action", choices=["tout", "collecter", "resumer", "audio", "site", "notifier", "tester-ia",
                                      "deja_collecte", "reste_rattrapage"], nargs="?", default="tout")
    p.add_argument("--essai", action="store_true", help="notifier : affiche les notifications sans les envoyer")
    p.add_argument("--forcer", action="store_true", help="notifier : envoie même hors de la plage horaire")
    p.add_argument("--config", default=None, help="chemin vers config.yaml")
    p.add_argument("--inline", action="store_true", help="site en un seul fichier HTML (aperçu hors-ligne)")
    p.add_argument("--rattrapage", action="store_true",
                   help="resumer : rattrapage des fiches IA, réglages ia.rattrapage de config.yaml")
    p.add_argument("--duree", type=int, default=None, help="resumer : durée maximale en minutes (rattrapage)")
    p.add_argument("--lots", type=int, default=None, help="resumer : nombre maximal de requêtes (rattrapage)")
    p.add_argument("-v", "--verbeux", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbeux else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    cfg = charger_config(args.config)
    from . import pipeline, resume_ia, sante, site
    if args.rattrapage:                         # réglages ia.rattrapage (durée limitée : la file reste libre)
        resume_ia.reglages_rattrapage(cfg)
    if args.duree:
        cfg.setdefault("ia", {})["duree_max_minutes"] = args.duree
    if args.lots:
        cfg.setdefault("ia", {})["max_requetes_par_execution"] = args.lots

    if args.action == "deja_collecte":         # une seule ligne sur stdout, lue par le workflow
        print("fait=oui" if pipeline.collecte_du_jour_faite(cfg) else "fait=non")
        return
    if args.action == "reste_rattrapage":      # idem : reste=N, lu par le rattrapage automatique du soir
        print(f"reste={resume_ia.reste_rattrapage(cfg)}")
        return
    if args.action == "tout":
        sante.RELEVE = sante.Releve()          # relevé du passage, pour repérer les pannes qui durent
    if args.action in ("tout", "collecter"):
        pipeline.collecter(cfg)
    if args.action in ("tout", "resumer"):
        resume_ia.resumer(cfg)
    if args.action == "tout":
        sante.RELEVE.enregistrer()
        sante.verifier(cfg)
    if args.action in ("tout", "audio"):
        from . import audio
        audio.generer(cfg)                    # n'échoue jamais : au pire, pas de MP3 aujourd'hui
    if args.action in ("tout", "site"):
        site.construire(cfg, inline=args.inline)
    if args.action == "tester-ia":
        resume_ia.tester(cfg)
    if args.action == "notifier":
        from . import notifications
        notifications.notifier(cfg, essai=args.essai, forcer=args.forcer)
        if not args.essai:
            sante.verifier(cfg, avec_retard=True)   # la collecte du matin a-t-elle bien tourné ?


if __name__ == "__main__":
    main()
