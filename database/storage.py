
"""Stockage de l'application : Supabase en ligne, JSON en local.
Sur Streamlit Cloud, configurer [supabase] dans les secrets pour une persistance réelle.
"""
import json
import os
from pathlib import Path
import streamlit as st

COLLECTIONS = [
    "clients", "devis", "factures", "paiements", "produits",
    "profiles_pvc", "vitrages", "accessoires", "parametres"
]

DEFAULTS = {
    "clients": [], "devis": [], "factures": [], "paiements": [], "produits": [],
    "profiles_pvc": [{"id":"pvc_standard","nom":"Profilé PVC standard","prix_ml":6000.0,"actif":True}],
    "vitrages": [
        {"id":"vit_simple","nom":"Vitrage simple","prix_m2":2500.0,"actif":True},
        {"id":"vit_double","nom":"Double vitrage","prix_m2":4500.0,"actif":True},
        {"id":"vit_teinte","nom":"Vitrage teinté","prix_m2":4000.0,"actif":True},
    ],
    "accessoires": [
        {"id":"acc_poignee","nom":"Poignée","unite":"pièce","prix_unitaire":800.0,"actif":True},
        {"id":"acc_paume","nom":"Paumelle","unite":"pièce","prix_unitaire":500.0,"actif":True},
        {"id":"acc_serrure","nom":"Serrure","unite":"pièce","prix_unitaire":1500.0,"actif":True},
    ],
    "parametres": {
        "entreprise_nom":"Atelier PVC Pro","entreprise_adresse":"","entreprise_telephone":"",
        "entreprise_email":"","conditions_paiement":"Selon accord avec le client.",
        "validite_devis_jours":30,"taux_taxe":0.0,"taxe_active":False,
        "regle_un_vantail":"cadre_seul","prefixe_devis":"DEV","prefixe_facture":"FAC"
    }
}

class Store:
    def __init__(self):
        self.local_dir = Path(os.environ.get("ATELIER_PVC_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
        self.local_dir.mkdir(parents=True, exist_ok=True)
        self.remote = False
        self.client = None
        try:
            if "supabase" in st.secrets:
                from supabase import create_client
                cfg = st.secrets["supabase"]
                self.client = create_client(cfg["url"], cfg["key"])
                self.remote = True
        except Exception:
            # Ne jamais empêcher l'application de démarrer si les secrets ne sont pas configurés.
            self.client = None
            self.remote = False
        if not self.remote:
            self._init_local()

    def _init_local(self):
        for name, default in DEFAULTS.items():
            path = self.local_dir / f"{name}.json"
            if not path.exists():
                self._write_local(name, default)

    def _write_local(self, name, data):
        path = self.local_dir / f"{name}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def load(self, name):
        if name not in COLLECTIONS:
            raise ValueError("Collection inconnue.")
        if self.remote:
            result = self.client.table("app_data").select("payload").eq("collection", name).execute()
            if result.data:
                return result.data[0]["payload"]
            default = DEFAULTS[name]
            self.save(name, default)
            return default
        path = self.local_dir / f"{name}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Lecture impossible pour {name}.json : {exc}") from exc

    def save(self, name, data):
        if name not in COLLECTIONS:
            raise ValueError("Collection inconnue.")
        if name == "parametres":
            if not isinstance(data, dict):
                raise ValueError("Les paramètres doivent être un objet.")
        elif not isinstance(data, list):
            raise ValueError(f"La collection {name} doit être une liste.")
        if self.remote:
            existing = self.client.table("app_data").select("id").eq("collection", name).execute()
            payload = {"collection": name, "payload": data}
            if existing.data:
                self.client.table("app_data").update({"payload": data}).eq("collection", name).execute()
            else:
                self.client.table("app_data").insert(payload).execute()
        else:
            self._write_local(name, data)

    def export_all(self):
        return {name: self.load(name) for name in COLLECTIONS}

    def restore_all(self, payload):
        if not isinstance(payload, dict) or any(k not in payload for k in COLLECTIONS):
            raise ValueError("Sauvegarde invalide ou incomplète.")
        for name in COLLECTIONS:
            self.save(name, payload[name])
