
```python
import json
from datetime import date
from uuid import uuid4
import pandas as pd
import streamlit as st
from database.storage import Store, COLLECTIONS
from services.calculs import calculer_metrage_pvc, calculer_surface_vitrage, calculer_total
from services.pdf_service import generer_pdf

st.set_page_config(page_title="Atelier PVC Pro", page_icon="🪟", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1500px;}
div[data-testid="stMetric"] {background:#fff;border:1px solid #e3eaf2;padding:16px;border-radius:12px;}
section[data-testid="stSidebar"] {border-right:1px solid #e5eaf0;}
h1,h2,h3 {letter-spacing:-.02em;}
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_store():
    return Store()

store = get_store()

def load(name):
    return store.load(name)

def save(name, value):
    store.save(name, value)

def money(v):
    return f"{float(v):,.2f} DA".replace(",", " ")

def next_number(items, prefix):
    year = date.today().year
    nums = []
    for item in items:
        n = str(item.get("numero", ""))
        if n.startswith(f"{prefix}-{year}-"):
            try: nums.append(int(n.rsplit("-",1)[1]))
            except ValueError: pass
    return f"{prefix}-{year}-{max(nums, default=0)+1:04d}"

params = load("parametres")
with st.sidebar:
    st.markdown("# 🪟 Atelier PVC Pro")
    st.caption("Devis · Factures · Gestion d'atelier")
    page = st.radio("Navigation", [
        "Tableau de bord", "Clients", "Nouveau devis", "Devis et factures",
        "Catalogue et tarifs", "Accessoires", "Paramètres", "Sauvegarde"
    ])
    st.divider()
    if store.remote:
        st.success("Stockage en ligne connecté")
    else:
        st.warning("Stockage JSON local")
        st.caption("Sur Streamlit Cloud, configure Supabase pour conserver les données.")

clients = load("clients")
devis = load("devis")
factures = load("factures")
paiements = load("paiements")
profiles = load("profiles_pvc")
vitrages = load("vitrages")
accessoires = load("accessoires")

def add_client(nom, telephone, email, adresse, ville):
    if not nom.strip():
        st.error("Le nom du client est obligatoire.")
        return
    if any(c.get("nom","").strip().casefold() == nom.strip().casefold() and c.get("telephone","") == telephone for c in clients):
        st.error("Un client similaire existe déjà.")
        return
    clients.append({"id":uuid4().hex, "nom":nom.strip(), "telephone":telephone.strip(),
                    "email":email.strip(), "adresse":adresse.strip(), "ville":ville.strip(),
                    "date_creation":date.today().isoformat(), "actif":True})
    save("clients", clients)
    st.success("Client enregistré.")

if page == "Tableau de bord":
    st.title("Tableau de bord")
    st.write(f"Bienvenue dans **{params.get('entreprise_nom','Atelier PVC Pro')}**.")
    total_factures = sum(float(f.get("total_ttc",0)) for f in factures)
    total_paye = sum(float(p.get("montant",0)) for p in paiements)
    reste = max(total_factures-total_paye, 0)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Clients", len(clients))
    c2.metric("Devis", len(devis))
    c3.metric("Total facturé", money(total_factures))
    c4.metric("Reste estimé à encaisser", money(reste))
    st.subheader("Derniers devis")
    if devis:
        st.dataframe(pd.DataFrame(devis).sort_values("date", ascending=False).head(8), use_container_width=True, hide_index=True)
    else:
        st.info("Aucun devis pour le moment. Commence par ajouter un client, puis crée un devis.")

elif page == "Clients":
    st.title("Gestion des clients")
    with st.expander("➕ Ajouter un client", expanded=not clients):
        with st.form("client_form", clear_on_submit=True):
            a,b = st.columns(2)
            nom = a.text_input("Nom ou raison sociale *")
            telephone = b.text_input("Téléphone")
            email = a.text_input("E-mail")
            ville = b.text_input("Ville / Wilaya")
            adresse = st.text_area("Adresse")
            submitted = st.form_submit_button("Enregistrer le client", type="primary")
            if submitted:
                add_client(nom, telephone, email, adresse, ville)
                st.rerun()
    st.subheader("Clients enregistrés")
    search = st.text_input("Rechercher par nom, téléphone ou ville")
    filtered = [c for c in clients if search.casefold() in " ".join(str(c.get(k,"")) for k in ("nom","telephone","ville")).casefold()]
    if filtered:
        st.dataframe(pd.DataFrame(filtered), use_container_width=True, hide_index=True)
        with st.expander("Modifier ou archiver un client"):
            selected = st.selectbox("Client", filtered, format_func=lambda x: f"{x['nom']} — {x.get('telephone','')}")
            with st.form("edit_client"):
                n = st.text_input("Nom", selected.get("nom",""))
                t = st.text_input("Téléphone", selected.get("telephone",""))
                e = st.text_input("E-mail", selected.get("email",""))
                ad = st.text_input("Adresse", selected.get("adresse",""))
                v = st.text_input("Ville", selected.get("ville",""))
                active = st.checkbox("Client actif", value=selected.get("actif",True))
                if st.form_submit_button("Enregistrer les modifications"):
                    for c in clients:
                        if c["id"] == selected["id"]:
                            c.update({"nom":n.strip(),"telephone":t.strip(),"email":e.strip(),"adresse":ad.strip(),"ville":v.strip(),"actif":active})
                    save("clients", clients); st.success("Client mis à jour."); st.rerun()
    else:
        st.info("Aucun client correspondant.")

elif page == "Nouveau devis":
    st.title("Créer un devis global")
    st.caption("Sélectionnez un seul client, ajoutez plusieurs produits. Le 1er s'additionne au 2ème, au 3ème, etc. Un seul total et un seul PDF.")

    if not clients:
        st.warning("Ajoute d'abord un client dans la rubrique Clients.")
    else:
        if "lignes_devis_cours" not in st.session_state:
            st.session_state.lignes_devis_cours = []
        if "edit_ligne_id" not in st.session_state:
            st.session_state.edit_ligne_id = None
        if "devis_client_id" not in st.session_state:
            st.session_state.devis_client_id = None

        actifs = [c for c in clients if c.get("actif", True)]
        client = st.selectbox("Client *", actifs, format_func=lambda c: f"{c['nom']} — {c.get('telephone','')}")

        # Garde le même client pour tout le panier
        if st.session_state.devis_client_id is None:
            st.session_state.devis_client_id = client["id"]
        if st.session_state.lignes_devis_cours and st.session_state.devis_client_id != client["id"]:
            st.warning(f"Panier en cours pour un autre client ({len(st.session_state.lignes_devis_cours)} ligne(s)). Changer de client va vider le panier.")
            c1,c2 = st.columns(2)
            if c1.button("🗑️ Vider le panier et changer de client"):
                st.session_state.lignes_devis_cours = []
                st.session_state.edit_ligne_id = None
                st.session_state.devis_client_id = client["id"]
                st.rerun()
            if c2.button("Annuler"):
                st.rerun()
            st.stop()

        # Récupération ligne en édition
        edit_data = None
        if st.session_state.edit_ligne_id:
            edit_data = next((l for l in st.session_state.lignes_devis_cours if l.get("ligne_id") == st.session_state.edit_ligne_id), None)
            if edit_data:
                st.info(f"✏️ Modification : **{edit_data['designation']}** — modifiez puis cliquez sur *Mettre à jour la ligne*")

        def get_def(key, default):
            return edit_data.get(key, default) if edit_data else default

        st.subheader("Ajouter une menuiserie / rideau")
        with st.container(border=True):
            a,b,c = st.columns(3)
            categories = ["Fenêtre","Porte-fenêtre","Baie vitrée","Rideau manuel","Rideau motorisé","Porte PVC","Imposte"]
            cat_default = get_def("categorie", "Fenêtre")
            cat_index = categories.index(cat_default) if cat_default in categories else 0
            categorie = a.selectbox("Type de produit", categories, index=cat_index, key="cat_select")
            
            # Désignation : si édition on extrait la partie après " — "
            des_raw = get_def("designation", "Menuiserie PVC")
            if edit_data and " — " in des_raw:
                des_raw = des_raw.split(" — ", 1)[1]
            designation = b.text_input("Désignation", value=des_raw, key="des_input")
            quantite = c.number_input("Quantité", min_value=1, max_value=1000, value=int(get_def("quantite",1)), step=1, key="qte_input")

            a,b,c = st.columns(3)
            largeur = a.number_input("Largeur (m)", min_value=0.01, max_value=20.0, value=float(get_def("largeur",1.20)), step=0.05, format="%.2f", key="larg_input")
            hauteur = b.number_input("Hauteur (m)", min_value=0.01, max_value=20.0, value=float(get_def("hauteur",1.40)), step=0.05, format="%.2f", key="haut_input")
            est_rideau = categorie in ("Rideau manuel", "Rideau motorisé")

            # Variables par défaut
            vantaux = 1
            ouverture = "Non applicable"
            vitrage = {"nom": "Non applicable", "prix_m2": 0}
            profil = {"nom": "Rideau", "prix_ml": 0}
            prix_ml = 0.0
            prix_m2 = 0.0
            mode_vitrage = "Surface brute"
            largeur_v, hauteur_v, nb_vitrages = largeur, hauteur, 1
            profil_extra = 0.0
            prix_rideau_m2 = float(get_def("prix_rideau_m2", 6000.0))

            if est_rideau:
                st.markdown("**Calcul du rideau au m²**")
                st.caption("Surface = largeur × hauteur. Prix saisi en DA/m². Formule : surface × prix_m2 × quantité")
                prix_rideau_m2 = st.number_input("Prix du rideau (DA/m²)", min_value=0.0, value=prix_rideau_m2, step=100.0, key="prix_rideau_m2")
                surface_rideau_unitaire = largeur * hauteur
                surface_rideau_totale = surface_rideau_unitaire * int(quantite)
                prix_unitaire_preview = surface_rideau_unitaire * prix_rideau_m2
                total_preview = prix_unitaire_preview * int(quantite)
                st.success(f"Surface unitaire : {surface_rideau_unitaire:.2f} m² | Prix unitaire : {money(prix_unitaire_preview)} | Prix total ligne : {money(total_preview)} — Ex: 2m x 2.5m = 5m² x 6000 = 30000 DA x2 = 60000 DA")
            else:
                vantaux = c.number_input("Nombre de vantaux", min_value=1, max_value=12, value=int(get_def("nb_vantaux",2)), step=1, key="vant_input")
                a,b,c = st.columns(3)
                ouverture_val = get_def("ouverture","Coulissant")
                ouverture_opts = ["Coulissant","Ouverture simple","Oscillo-battant","Autre"]
                ouverture = a.selectbox("Ouverture", ouverture_opts, index=ouverture_opts.index(ouverture_val) if ouverture_val in ouverture_opts else 0, key="ouv_input")
                vitrage = b.selectbox("Vitrage", vitrages, format_func=lambda x: x["nom"], key="vit_input")
                profil = c.selectbox("Profilé PVC", profiles, format_func=lambda x: f"{x['nom']} ({money(x['prix_ml'])}/ml)", key="prof_input")
                a,b,c = st.columns(3)
                prix_ml = a.number_input("Prix PVC (DA/ml)", min_value=0.0, value=float(get_def("prix_vitrage_m2", profil.get("prix_ml",6000)) if False else float(profil.get("prix_ml",6000))), step=100.0, key="prixml_input")
                # Pour garder le prix édité si on est en édition
                if edit_data and edit_data.get("cout_pvc",0) > 0:
                    prix_ml = a.number_input("Prix PVC (DA/ml)", min_value=0.0, value=float(edit_data.get("details_metrage",{}).get("prix_ml", profil.get("prix_ml",6000))), step=100.0, key="prixml_edit")
                prix_m2 = b.number_input("Prix vitrage (DA/m²)", min_value=0.0, value=float(get_def("prix_vitrage_m2", vitrage.get("prix_m2",2500))), step=100.0, key="prixm2_input")
                mode_opts = ["Surface brute", "Dimensions réelles - manuel", "Dimensions réelles - automatique"]
                mode_v = get_def("mode_vitrage","Surface brute")
                mode_vitrage = c.selectbox("Mode de calcul du vitrage", mode_opts, index=mode_opts.index(mode_v) if mode_v in mode_opts else 0, key="modevit_input")

                if mode_vitrage == "Dimensions réelles - manuel":
                    st.markdown("**Dimensions réelles du verre**")
                    a, b, c = st.columns(3)
                    largeur_v = a.number_input("Largeur du verre (m)", min_value=0.001, value=float(get_def("largeur_v",1.10)), step=0.01, format="%.3f", key="lv_man")
                    hauteur_v = b.number_input("Hauteur du verre (m)", min_value=0.001, value=float(get_def("hauteur_v",1.30)), step=0.01, format="%.3f", key="hv_man")
                    nb_vitrages = c.number_input("Nombre de vitrages par menuiserie", min_value=1, max_value=20, value=int(get_def("nb_vitrages", vantaux)), step=1, key="nbv_man")
                elif mode_vitrage == "Dimensions réelles - automatique":
                    st.markdown("**Calcul automatique des dimensions du verre**")
                    st.caption("Déductions en millimètres. Vitrages de même largeur.")
                    a, b, c = st.columns(3)
                    nb_vitrages = a.number_input("Nombre de vitrages par menuiserie", min_value=1, max_value=20, value=int(get_def("nb_vitrages", vantaux)), step=1, key="nbv_auto")
                    deduction_largeur_mm = b.number_input("Déduction totale en largeur (mm)", min_value=0.0, value=100.0, step=5.0, key="dedl_auto")
                    deduction_hauteur_mm = c.number_input("Déduction totale en hauteur (mm)", min_value=0.0, value=100.0, step=5.0, key="dedh_auto")
                    largeur_v = largeur / int(nb_vitrages) - deduction_largeur_mm / 1000
                    hauteur_v = hauteur - deduction_hauteur_mm / 1000
                    if largeur_v > 0 and hauteur_v > 0:
                        st.info(f"Dimensions calculées par vitrage : {largeur_v:.3f} m × {hauteur_v:.3f} m")
                    else:
                        st.error("Déductions trop importantes : vérifie les dimensions.")
                else:
                    largeur_v, hauteur_v, nb_vitrages = largeur, hauteur, 1

            st.markdown("**Accessoires**")
            choix_accessoires = st.multiselect("Ajouter des accessoires", accessoires, format_func=lambda x: f"{x['nom']} — {money(x['prix_unitaire'])}/{x.get('unite','unité')}", key="acc_multi")
            accessoires_qte = {}
            for acc in choix_accessoires:
                accessoires_qte[acc["id"]] = st.number_input(f"Quantité par menuiserie : {acc['nom']}", min_value=0, max_value=100, value=1, key=f"acc_{acc['id']}")

            a,b,c = st.columns(3)
            autres = a.number_input("Fabrication / pose (DA)", min_value=0.0, value=float(get_def("autres_couts", params.get("frais_pose_par_defaut",0))), step=500.0, key="autres_input")
            remise = b.number_input("Remise (DA)", min_value=0.0, value=float(get_def("remise",0.0)), step=100.0, key="remise_input")
            if not est_rideau:
                profil_extra = c.number_input("Profilés supplémentaires (ml/unité)", min_value=0.0, value=float(get_def("profil_extra",0.0)), step=0.1, key="extra_input")

            col_add, col_cancel = st.columns([3,1])
            label_btn = "✅ Mettre à jour la ligne" if st.session_state.edit_ligne_id else "➕ Ajouter au devis (s'additionne)"
            if col_add.button(label_btn, type="primary", use_container_width=True):
                try:
                    # Validation vitrage
                    if not est_rideau and (largeur_v <= 0 or hauteur_v <= 0):
                        st.error("Dimensions vitrage invalides.")
                        st.stop()
                    if largeur <= 0 or hauteur <= 0 or quantite <=0:
                        st.error("Largeur, hauteur et quantité doivent être > 0")
                        st.stop()

                    if est_rideau:
                        surface_rideau_unitaire = largeur * hauteur
                        surface_rideau_totale = surface_rideau_unitaire * int(quantite)
                        cout_rideau = surface_rideau_totale * float(prix_rideau_m2)
                        metrage = {"ml_total": 0.0, "ml_total_unitaire": 0.0, "ml_cadre": 0.0, "ml_horizontaux_ouvrants": 0.0, "ml_verticaux_ouvrants": 0.0, "cout_pvc_total": 0.0, "prix_ml": 0.0}
                        surf = {"surface_totale": surface_rideau_totale, "surface_unitaire": surface_rideau_unitaire}
                        cout_vit = cout_rideau
                    else:
                        regle = params.get("regle_un_vantail","cadre_seul")
                        metrage = calculer_metrage_pvc(largeur, hauteur, int(vantaux), float(prix_ml), int(quantite), regle, float(profil_extra))
                        surf = calculer_surface_vitrage(largeur, hauteur, int(quantite), "dimensions_reelles" if mode_vitrage != "Surface brute" else "brute", float(largeur_v), float(hauteur_v), int(nb_vitrages))
                        cout_vit = surf["surface_totale"] * float(prix_m2)
                        cout_rideau = 0.0
                        surface_rideau_unitaire = 0.0
                        surface_rideau_totale = 0.0

                    cout_acc_unitaire = sum(float(a["prix_unitaire"])*accessoires_qte.get(a["id"],0) for a in choix_accessoires)
                    cout_acc_total = cout_acc_unitaire * int(quantite)
                    total = calculer_total(metrage["cout_pvc_total"], cout_vit, cout_acc_total, float(autres), float(remise), params.get("taxe_active",False), params.get("taux_taxe",0))

                    # Prix unitaire pour affichage tableau
                    prix_unitaire = total["total_ttc"] / int(quantite) if int(quantite) >0 else total["total_ttc"]
                    # Si rideau on force le prix unitaire théorique
                    if est_rideau:
                        prix_unitaire = surface_rideau_unitaire * float(prix_rideau_m2) + (cout_acc_unitaire + float(autres)/int(quantite) - float(remise)/int(quantite))

                    ligne = {
                        "ligne_id": st.session_state.edit_ligne_id if st.session_state.edit_ligne_id else uuid4().hex,
                        "designation": f"{categorie} — {designation}",
                        "categorie": categorie,
                        "largeur": float(largeur), "hauteur": float(hauteur), "quantite": int(quantite),
                        "nb_vantaux": int(vantaux) if not est_rideau else 1,
                        "ouverture": ouverture,
                        "vitrage": vitrage["nom"] if not est_rideau else "Non applicable",
                        "surface_vitrage": 0.0 if est_rideau else float(surf["surface_totale"]),
                        "surface_vitrage_unitaire": 0.0 if est_rideau else float(surf["surface_totale"]/int(quantite)),
                        "prix_vitrage_m2": float(prix_m2) if not est_rideau else 0.0,
                        "type_tarification": "surface_m2" if est_rideau else "vitrage",
                        "surface_rideau": float(surf["surface_totale"]) if est_rideau else 0.0,
                        "surface_rideau_unitaire": float(surface_rideau_unitaire) if est_rideau else 0.0,
                        "prix_rideau_m2": float(prix_rideau_m2) if est_rideau else 0.0,
                        "cout_rideau": round(float(cout_rideau),2),
                        "ml_total": float(metrage["ml_total"]),"ml_unitaire": float(metrage["ml_total_unitaire"]),
                        "cout_pvc": float(metrage["cout_pvc_total"]),"cout_vitrage": round(float(cout_vit),2),
                        "cout_accessoires": round(float(cout_acc_total),2),
                        "accessoires": [{"nom":a["nom"],"quantite_par_unite":accessoires_qte[a["id"]],"prix_unitaire":a["prix_unitaire"]} for a in choix_accessoires],
                        "autres_couts": float(autres),"remise": float(remise),
                        "total_ligne": float(total["total_ttc"]),
                        "prix_unitaire": round(float(prix_unitaire),2),
                        "details_metrage": metrage,
                        "mode_vitrage": mode_vitrage,
                        "largeur_v": float(largeur_v), "hauteur_v": float(hauteur_v), "nb_vitrages": int(nb_vitrages),
                        "profil_extra": float(profil_extra)
                    }

                    if st.session_state.edit_ligne_id:
                        # Remplacement
                        for idx, l in enumerate(st.session_state.lignes_devis_cours):
                            if l.get("ligne_id") == st.session_state.edit_ligne_id:
                                st.session_state.lignes_devis_cours[idx] = ligne
                                break
                        st.session_state.edit_ligne_id = None
                        st.success("Ligne mise à jour.")
                    else:
                        st.session_state.lignes_devis_cours.append(ligne)
                        st.success(f"Produit ajouté : {ligne['designation']} — {money(ligne['total_ligne'])}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Impossible de calculer : {exc}")

            if st.session_state.edit_ligne_id and col_cancel.button("Annuler modification", use_container_width=True):
                st.session_state.edit_ligne_id = None
                st.rerun()

        # --- TABLEAU RECAPITULATIF GLOBAL ---
        if st.session_state.lignes_devis_cours:
            st.divider()
            st.subheader(f"Récapitulatif du devis ({len(st.session_state.lignes_devis_cours)} produits)")
            
            # Construction tableau demandé
            rows = []
            for i, l in enumerate(st.session_state.lignes_devis_cours, 1):
                dims = f"{l['largeur']:.2f} x {l['hauteur']:.2f} m"
                # ml et surfaces conditionnels
                ml = f"{l['ml_total']:.2f}" if l['ml_total']>0 else "—"
                surf_v = f"{l['surface_vitrage']:.2f}" if l['surface_vitrage']>0 else "—"
                surf_r = f"{l['surface_rideau']:.2f}" if l['surface_rideau']>0 else "—"
                rows.append({
                    "N°": i,
                    "Désignation": l["designation"],
                    "Type": l["categorie"],
                    "Dimensions": dims,
                    "Qté": l["quantite"],
                    "ML PVC": ml,
                    "Surface vitrage (m²)": surf_v,
                    "Surface rideau (m²)": surf_r,
                    "Prix unitaire": money(l["prix_unitaire"]),
                    "Prix total": money(l["total_ligne"])
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            total_general = sum(float(l["total_ligne"]) for l in st.session_state.lignes_devis_cours)
            m1,m2,m3 = st.columns(3)
            m1.metric("Nombre de lignes", len(st.session_state.lignes_devis_cours))
            m2.metric("Total général HT/TTC", money(total_general))
            m3.metric("Client", client["nom"])

            # Actions modifier / supprimer
            st.markdown("**Gérer les lignes :**")
            for l in st.session_state.lignes_devis_cours:
                c1,c2,c3,c4 = st.columns([5,2,2,1])
                c1.write(f"**{l['designation']}** — {l['largeur']:.2f}x{l['hauteur']:.2f} m x{l['quantite']} = **{money(l['total_ligne'])}**")
                if c2.button("✏️ Modifier", key=f"edit_{l['ligne_id']}"):
                    st.session_state.edit_ligne_id = l["ligne_id"]
                    st.rerun()
                if c3.button("🗑️ Supprimer", key=f"
