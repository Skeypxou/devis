
"""Calculs métier : toutes les dimensions sont en mètres, les tarifs en DA."""
from math import isfinite

def _num(value, label, allow_zero=False):
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} doit être numérique.")
    if not isfinite(x) or x < 0 or (not allow_zero and x == 0):
        raise ValueError(f"{label} doit être {'positif ou nul' if allow_zero else 'strictement positif'}.")
    return x

def calculer_metrage_pvc(largeur, hauteur, nb_vantaux=1, prix_ml=0, quantite=1,
                         regle_un_vantail="cadre_seul", profil_extra_ml=0):
    L = _num(largeur, "Largeur")
    H = _num(hauteur, "Hauteur")
    P = _num(prix_ml, "Prix PVC", True)
    Qf = _num(quantite, "Quantité")
    Nf = _num(nb_vantaux, "Nombre de vantaux")
    extra = _num(profil_extra_ml, "Profilés supplémentaires", True)
    Q, N = int(Qf), int(Nf)
    if Q != Qf or N != Nf or Q < 1 or N < 1 or N > 12:
        raise ValueError("La quantité doit être entière et positive ; les vantaux doivent être entre 1 et 12.")
    cadre = 2 * L + 2 * H
    if N == 1 and regle_un_vantail == "cadre_seul":
        horiz = vert = 0.0
        total_u = cadre + extra
    else:
        horiz = 2 * N * (L / N)
        vert = 2 * N * H
        total_u = cadre + horiz + vert + extra
    return {
        "ml_cadre": round(cadre, 4),
        "ml_horizontaux_ouvrants": round(horiz, 4),
        "ml_verticaux_ouvrants": round(vert, 4),
        "ml_profil_extra": round(extra, 4),
        "ml_total_unitaire": round(total_u, 4),
        "ml_total": round(total_u * Q, 4),
        "prix_ml": round(P, 2),
        "cout_pvc_unitaire": round(total_u * P, 2),
        "cout_pvc_total": round(total_u * Q * P, 2),
        "quantite": Q,
        "nb_vantaux": N,
    }

def calculer_surface_vitrage(largeur, hauteur, quantite=1, mode="brute",
                             largeur_vitrage=None, hauteur_vitrage=None, nb_vitrages=1):
    Qf = _num(quantite, "Quantité")
    if int(Qf) != Qf or Qf < 1:
        raise ValueError("La quantité doit être un entier positif.")
    if mode == "dimensions_reelles":
        L = _num(largeur_vitrage, "Largeur du vitrage")
        H = _num(hauteur_vitrage, "Hauteur du vitrage")
        nf = _num(nb_vitrages, "Nombre de vitrages")
        if int(nf) != nf or nf < 1:
            raise ValueError("Le nombre de vitrages doit être un entier positif.")
        surface = L * H * int(nf)
    else:
        surface = _num(largeur, "Largeur") * _num(hauteur, "Hauteur")
    return {"surface_unitaire": round(surface, 4), "surface_totale": round(surface * int(Qf), 4)}

def calculer_total(cout_pvc, cout_vitrage, cout_accessoires=0, autres_couts=0,
                   remise=0, taxe_active=False, taux_taxe=0):
    vals = [float(cout_pvc), float(cout_vitrage), float(cout_accessoires), float(autres_couts), float(remise)]
    if any(not isfinite(v) or v < 0 for v in vals):
        raise ValueError("Les montants doivent être positifs ou nuls.")
    brut = sum(vals[:4])
    remise = min(vals[4], brut)
    ht = round(brut - remise, 2)
    taux = _num(taux_taxe, "Taux de taxe", True)
    taxe = round(ht * taux / 100, 2) if taxe_active else 0.0
    return {"sous_total": round(brut, 2), "remise": round(remise, 2),
            "total_ht": ht, "taxe": taxe, "total_ttc": round(ht + taxe, 2)}
