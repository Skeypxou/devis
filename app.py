
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
        # Panier temporaire : plusieurs produits dans un seul devis
    if "panier_devis" not in st.session_state:
        st.session_state["panier_devis"] = []

    if "panier_client_id" not in st.session_state:
        st.session_state["panier_client_id"] = None
    st.title("Créer un devis")
    if not clients:
        st.warning("Ajoute d'abord un client dans la rubrique Clients.")
    else:
        client = st.selectbox("Client", [c for c in clients if c.get("actif",True)], format_func=lambda c: f"{c['nom']} — {c.get('telephone','')}")
        st.subheader("Menuiserie")
        with st.container():
            a,b,c = st.columns(3)
            categorie = a.selectbox("Type de produit", ["Fenêtre","Porte-fenêtre","Baie vitrée","Rideau manuel","Rideau motorisé","Porte PVC","Imposte"])
            designation = b.text_input("Désignation", value="Menuiserie PVC")
            quantite = c.number_input("Quantité", min_value=1, max_value=1000, value=1, step=1)
            a,b,c = st.columns(3)
            largeur = a.number_input("Largeur (m)", min_value=0.01, max_value=20.0, value=1.20, step=0.05, format="%.2f")
            hauteur = b.number_input("Hauteur (m)", min_value=0.01, max_value=20.0, value=1.40, step=0.05, format="%.2f")
            est_rideau = categorie in ("Rideau manuel", "Rideau motorisé", "Rideau électrique")

            if est_rideau:
                st.markdown("**Calcul du rideau au mètre carré**")
                st.caption("Surface = largeur × hauteur. Le prix est saisi en dinars algériens par m².")
                prix_rideau_m2 = st.number_input("Prix du rideau (DA/m²)", min_value=0.0, value=6000.0, step=100.0, key="prix_rideau_m2")
                surface_rideau_unitaire = largeur * hauteur
                surface_rideau_totale = surface_rideau_unitaire * int(quantite)
                st.info(f"Surface par rideau : {surface_rideau_unitaire:.2f} m² · Surface totale : {surface_rideau_totale:.2f} m² · Prix total : {money(surface_rideau_totale * prix_rideau_m2)}")
                # Valeurs neutres conservées pour que les autres champs de la ligne restent compatibles.
                vantaux = 1
                ouverture = "Non applicable"
                vitrage = {"nom": "Non applicable", "prix_m2": 0}
                profil = {"nom": "Rideau", "prix_ml": 0}
                prix_ml = 0.0
                prix_m2 = 0.0
                mode_vitrage = "Surface brute"
                largeur_v, hauteur_v, nb_vitrages = largeur, hauteur, 1
                profil_extra = 0.0
            else:
                vantaux = c.number_input("Nombre de vantaux", min_value=1, max_value=12, value=2, step=1)
                a,b,c = st.columns(3)
                ouverture = a.selectbox("Ouverture", ["Coulissant","Ouverture simple","Oscillo-battant","Autre"])
                vitrage = b.selectbox("Vitrage", vitrages, format_func=lambda x: x["nom"])
                profil = c.selectbox("Profilé PVC", profiles, format_func=lambda x: f"{x['nom']} ({money(x['prix_ml'])}/ml)")
                a,b,c = st.columns(3)
                prix_ml = a.number_input("Prix PVC (DA/ml)", min_value=0.0, value=float(profil.get("prix_ml",6000)), step=100.0)
                prix_m2 = b.number_input("Prix vitrage (DA/m²)", min_value=0.0, value=float(vitrage.get("prix_m2",2500)), step=100.0)
                mode_vitrage = c.selectbox(
                    "Mode de calcul du vitrage",
                    ["Surface brute", "Dimensions réelles - manuel", "Dimensions réelles - automatique"],
                )

                if mode_vitrage == "Dimensions réelles - manuel":
                    st.markdown("**Dimensions réelles du verre**")
                    a, b, c = st.columns(3)
                    largeur_v = a.number_input("Largeur du verre (m)", min_value=0.001, value=1.10, step=0.01, format="%.3f")
                    hauteur_v = b.number_input("Hauteur du verre (m)", min_value=0.001, value=1.30, step=0.01, format="%.3f")
                    nb_vitrages = c.number_input("Nombre de vitrages par menuiserie", min_value=1, max_value=20, value=int(vantaux), step=1)
                elif mode_vitrage == "Dimensions réelles - automatique":
                    st.markdown("**Calcul automatique des dimensions du verre**")
                    st.caption("Les déductions sont saisies en millimètres. Le calcul suppose des vitrages de même largeur.")
                    a, b, c = st.columns(3)
                    nb_vitrages = a.number_input("Nombre de vitrages par menuiserie", min_value=1, max_value=20, value=int(vantaux), step=1)
                    deduction_largeur_mm = b.number_input("Déduction totale en largeur (mm)", min_value=0.0, value=100.0, step=5.0)
                    deduction_hauteur_mm = c.number_input("Déduction totale en hauteur (mm)", min_value=0.0, value=100.0, step=5.0)
                    largeur_v = largeur / int(nb_vitrages) - deduction_largeur_mm / 1000
                    hauteur_v = hauteur - deduction_hauteur_mm / 1000
                    if largeur_v > 0 and hauteur_v > 0:
                        st.info(f"Dimensions calculées par vitrage : {largeur_v:.3f} m × {hauteur_v:.3f} m")
                    else:
                        st.error("Les déductions sont trop importantes : vérifie les dimensions et le nombre de vitrages.")
                else:
                    largeur_v, hauteur_v, nb_vitrages = largeur, hauteur, 1
            st.markdown("**Accessoires**")
            choix_accessoires = st.multiselect("Ajouter des accessoires", accessoires, format_func=lambda x: f"{x['nom']} — {money(x['prix_unitaire'])}/{x.get('unite','unité')}")
            accessoires_qte = {}
            for acc in choix_accessoires:
                accessoires_qte[acc["id"]] = st.number_input(f"Quantité par menuiserie : {acc['nom']}", min_value=0, max_value=100, value=1, key=f"acc_{acc['id']}")
            a,b,c = st.columns(3)
            autres = a.number_input("Fabrication / pose (DA)", min_value=0.0, value=float(params.get("frais_pose_par_defaut",0)), step=500.0)
            remise = b.number_input("Remise (DA)", min_value=0.0, value=0.0, step=100.0)
            if not est_rideau:
                profil_extra = c.number_input("Profilés supplémentaires (ml/unité)", min_value=0.0, value=0.0, step=0.1)
            observations = st.text_area("Observations / conditions particulières")
            submit_quote = st.button("➕ Ajouter ce produit au devis", type="primary")
        if submit_quote:
            try:
                if largeur_v <= 0 or hauteur_v <= 0:
                    st.error(
                        "Les dimensions du vitrage doivent être positives. "
                        "Réduis les déductions ou vérifie les dimensions."
                    )
                    st.stop()

                if est_rideau:
                    surface_rideau_unitaire = largeur * hauteur
                    surface_rideau_totale = surface_rideau_unitaire * int(quantite)
                    cout_rideau = surface_rideau_totale * prix_rideau_m2
                    metrage = {"ml_total": 0.0, "ml_total_unitaire": 0.0, "ml_cadre": 0.0,
                               "ml_horizontaux_ouvrants": 0.0, "ml_verticaux_ouvrants": 0.0,
                               "cout_pvc_total": 0.0}
                    surf = {"surface_totale": surface_rideau_totale}
                    cout_vit = cout_rideau  # Compatibilité avec le calcul total et les anciens modèles PDF.
                else:
                    if largeur_v <= 0 or hauteur_v <= 0:
                        st.error("Les dimensions du vitrage doivent être positives. Réduis les déductions ou vérifie les dimensions.")
                        st.stop()
                    regle = params.get("regle_un_vantail","cadre_seul")
                    metrage = calculer_metrage_pvc(largeur, hauteur, int(vantaux), prix_ml, int(quantite), regle, profil_extra)
                    surf = calculer_surface_vitrage(largeur, hauteur, int(quantite),
                        "dimensions_reelles" if mode_vitrage != "Surface brute" else "brute",
                        largeur_v, hauteur_v, int(nb_vitrages))
                    cout_vit = surf["surface_totale"] * prix_m2
                    cout_rideau = 0.0
                cout_acc_unitaire = sum(float(a["prix_unitaire"])*accessoires_qte[a["id"]] for a in choix_accessoires)
                cout_acc_total = cout_acc_unitaire * int(quantite)
                total = calculer_total(metrage["cout_pvc_total"], cout_vit, cout_acc_total, autres, remise,
                                       params.get("taxe_active",False), params.get("taux_taxe",0))
                ligne = {
                    "designation":f"{categorie} — {designation}", "categorie":categorie,
                    "largeur":float(largeur),"hauteur":float(hauteur),"quantite":int(quantite),
                    "nb_vantaux":int(vantaux),"ouverture":ouverture,"vitrage":vitrage["nom"],
                    "surface_vitrage": 0.0 if est_rideau else surf["surface_totale"],
                    "prix_vitrage_m2":float(prix_m2),
                    "type_tarification":"surface_m2" if est_rideau else "vitrage",
                    "surface_rideau":surf["surface_totale"] if est_rideau else 0.0,
                    "prix_rideau_m2":float(prix_rideau_m2) if est_rideau else 0.0,
                    "cout_rideau":round(cout_rideau,2),
                    "ml_total":metrage["ml_total"],"ml_unitaire":metrage["ml_total_unitaire"],
                    "cout_pvc":metrage["cout_pvc_total"],"cout_vitrage":round(cout_vit,2),
                    "cout_accessoires":round(cout_acc_total,2),"accessoires":[{"nom":a["nom"],"quantite_par_unite":accessoires_qte[a["id"]],"prix_unitaire":a["prix_unitaire"]} for a in choix_accessoires],
                    "autres_couts":float(autres),"remise":float(remise),
                    "total_ht_ligne": float(total["total_ht"]),
                    "taxe_ligne": float(total["taxe"]),
                    "total_ligne":total["total_ttc"],"details_metrage":metrage
                }
                doc =                # Éviter de mélanger les produits de clients différents
                panier_client = st.session_state["panier_client_id"]

                if st.session_state["panier_devis"] and panier_client != client["id"]:
                    st.warning(
                        "Le panier contient déjà les produits d'un autre client. "
                        "Enregistre le devis ou vide le panier avant de changer de client."
                    )
                else:
                    st.session_state["panier_client_id"] = client["id"]
                    ligne["id"] = uuid4().hex
                    st.session_state["panier_devis"].append(ligne)
                    st.success(
                        f"Produit ajouté : {ligne['designation']} "
                        f"(quantité : {ligne['quantite']})."
                    )
            except Exception as exc:
                st.error(f"Impossible de calculer le produit : {exc}")

        # Afficher les produits déjà ajoutés au devis
        panier = st.session_state["panier_devis"]

        if panier:
            st.divider()
            st.subheader("🧾 Produits du devis en cours")

            for index, produit in enumerate(panier):
                gauche, milieu, droite = st.columns([5, 2, 1])

                gauche.write(
                    f"**{index + 1}. {produit['designation']}**  \n"
                    f"Quantité : {produit['quantite']} · "
                    f"Dimensions : {produit['largeur']:.2f} × "
                    f"{produit['hauteur']:.2f} m"
                )
                milieu.write(money(produit["total_ligne"]))

                if droite.button("🗑️", key=f"retirer_produit_{produit['id']}"):
                    st.session_state["panier_devis"].pop(index)

                    if not st.session_state["panier_devis"]:
                        st.session_state["panier_client_id"] = None

                    st.rerun()

            total_panier = sum(
                float(p.get("total_ligne", 0))
                for p in panier
            )

            st.metric("TOTAL PROVISOIRE DU DEVIS", money(total_panier))

            col1, col2 = st.columns(2)

            with col1:
                if st.button(
                    "💾 Enregistrer le devis complet",
                    type="primary",
                    use_container_width=True,
                ):
                    client_panier = next(
                        (
                            c for c in clients
                            if c["id"] == st.session_state["panier_client_id"]
                        ),
                        None,
                    )

                    if client_panier is None:
                        st.error("Le client associé au panier est introuvable.")
                    else:
                        lignes_finales = [
                            dict(p) for p in st.session_state["panier_devis"]
                        ]

                        total_ht = sum(
                            float(p.get("total_ht_ligne", p.get("total_ligne", 0)))
                            for p in lignes_finales
                        )
                        taxe = sum(
                            float(p.get("taxe_ligne", 0))
                            for p in lignes_finales
                        )
                        total_ttc = sum(
                            float(p.get("total_ligne", 0))
                            for p in lignes_finales
                        )

                        doc = {
                            "id": uuid4().hex,
                            "numero": next_number(
                                devis, params.get("prefixe_devis", "DEV")
                            ),
                            "date": date.today().isoformat(),
                            "client_id": client_panier["id"],
                            "client_nom": client_panier["nom"],
                            "client_telephone": client_panier.get("telephone", ""),
                            "lignes": lignes_finales,
                            "total_ht": round(total_ht, 2),
                            "taxe": round(taxe, 2),
                            "total_ttc": round(total_ttc, 2),
                            "statut": "Brouillon",
                            "observations": observations,
                            "conditions": params.get("conditions_paiement", ""),
                            "type": "devis",
                        }

                        devis.append(doc)
                        save("devis", devis)

                        st.session_state["panier_devis"] = []
                        st.session_state["panier_client_id"] = None

                        st.success(
                            f"Devis {doc['numero']} enregistré avec "
                            f"{len(lignes_finales)} produit(s)."
                        )

                        pdf = generer_pdf(doc, params, "DEVIS")
                        st.download_button(
                            "📄 Télécharger le devis PDF",
                            data=pdf,
                            file_name=f"{doc['numero']}.pdf",
                            mime="application/pdf",
                            key=f"nouveau_pdf_{doc['id']}",
                        )

                        st.rerun()

            with col2:
                if st.button(
                    "Vider le panier",
                    use_container_width=True,
                ):
                    st.session_state["panier_devis"] = []
                    st.session_state["panier_client_id"] = None
                    st.rerun()
            except Exception as exc:
                st.error(f"Impossible de calculer le devis : {exc}")

elif page == "Devis et factures":
    st.title("Devis et factures")
    tab1,tab2,tab3 = st.tabs(["Devis enregistrés","Factures","Paiements"])
    with tab1:
        if devis:
            for d in reversed(devis):
                with st.expander(f"{d['numero']} · {d['client_nom']} · {money(d['total_ttc'])} · {d['statut']}"):
                    st.write(f"Date : {d['date']} | Observations : {d.get('observations','—')}")
                    st.dataframe(pd.DataFrame(d["lignes"]), use_container_width=True, hide_index=True)
                    pdf = generer_pdf(d,params,"DEVIS")
                    st.download_button("Télécharger PDF",pdf,file_name=f"{d['numero']}.pdf",mime="application/pdf",key=f"pdf_{d['id']}")
                    statuses = ["Brouillon","Envoyé","Accepté","Refusé","Expiré"]
                    status = st.selectbox("Statut",statuses,index=statuses.index(d["statut"]) if d["statut"] in statuses else 0,key=f"status_{d['id']}")
                    if st.button("Enregistrer le statut",key=f"save_status_{d['id']}"):
                        for item in devis:
                            if item["id"] == d["id"]: item["statut"] = status
                        save("devis",devis); st.rerun()
                    already = next((f for f in factures if f.get("devis_id")==d["id"]),None)
                    if d["statut"] == "Accepté" and not already:
                        if st.button("Convertir en facture",key=f"convert_{d['id']}",type="primary"):
                            f = dict(d)
                            f.update({"id":uuid4().hex,"numero":next_number(factures,params.get("prefixe_facture","FAC")),
                                      "date":date.today().isoformat(),"statut_paiement":"Non payée","devis_id":d["id"],"type":"facture"})
                            factures.append(f); save("factures",factures)
                            st.success(f"Facture {f['numero']} créée."); st.rerun()
                    elif already:
                        st.info(f"Facture déjà créée : {already['numero']}")
        else: st.info("Aucun devis enregistré.")
    with tab2:
        if factures:
            for f in reversed(factures):
                with st.expander(f"{f['numero']} · {f['client_nom']} · {money(f['total_ttc'])}"):
                    paid = sum(float(p["montant"]) for p in paiements if p["facture_id"]==f["id"])
                    st.write(f"Total : {money(f['total_ttc'])} · Payé : {money(paid)} · Reste : {money(max(f['total_ttc']-paid,0))}")
                    st.download_button("Télécharger facture PDF",generer_pdf(f,params,"FACTURE"),file_name=f"{f['numero']}.pdf",mime="application/pdf",key=f"facpdf_{f['id']}")
        else: st.info("Aucune facture.")
    with tab3:
        if not factures: st.info("Crée une facture avant d'enregistrer un paiement.")
        else:
            with st.form("payment_form"):
                facture = st.selectbox("Facture",factures,format_func=lambda f:f"{f['numero']} — {f['client_nom']} — {money(f['total_ttc'])}")
                montant = st.number_input("Montant reçu (DA)",min_value=0.01,value=1000.0,step=500.0)
                mode = st.selectbox("Mode de paiement",["Espèces","Virement","Chèque","Autre"])
                ref = st.text_input("Référence / observation")
                if st.form_submit_button("Enregistrer le paiement",type="primary"):
                    paid = sum(float(p["montant"]) for p in paiements if p["facture_id"]==facture["id"])
                    if paid + montant > float(facture["total_ttc"]) + 0.01:
                        st.error("Ce paiement dépasserait le montant de la facture.")
                    else:
                        paiements.append({"id":uuid4().hex,"facture_id":facture["id"],"numero_facture":facture["numero"],
                                          "montant":float(montant),"date":date.today().isoformat(),"mode":mode,"reference":ref})
                        save("paiements",paiements); st.success("Paiement enregistré."); st.rerun()
            if paiements:
                st.dataframe(pd.DataFrame(paiements),use_container_width=True,hide_index=True)

elif page == "Catalogue et tarifs":
    st.title("Profilés PVC et vitrages")
    tab1,tab2 = st.tabs(["Profilés PVC","Vitrages"])
    with tab1:
        with st.form("add_profile"):
            nom = st.text_input("Nom du profilé")
            prix = st.number_input("Prix (DA/ml)",min_value=0.0,value=6000.0,step=100.0)
            if st.form_submit_button("Ajouter le profilé"):
                if nom.strip():
                    profiles.append({"id":uuid4().hex,"nom":nom.strip(),"prix_ml":float(prix),"actif":True})
                    save("profiles_pvc",profiles); st.success("Profilé ajouté."); st.rerun()
                else: st.error("Le nom est obligatoire.")
        if profiles: st.dataframe(pd.DataFrame(profiles),use_container_width=True,hide_index=True)
        with st.expander("Modifier un prix de profilé"):
            p = st.selectbox("Profilé",profiles,format_func=lambda x:x["nom"],key="edit_p")
            newp = st.number_input("Nouveau prix DA/ml",min_value=0.0,value=float(p["prix_ml"]),step=100.0)
            if st.button("Mettre à jour le prix PVC"):
                for x in profiles:
                    if x["id"]==p["id"]: x["prix_ml"]=float(newp)
                save("profiles_pvc",profiles); st.rerun()
    with tab2:
        with st.form("add_glass"):
            nomv = st.text_input("Nom du vitrage")
            prixv = st.number_input("Prix (DA/m²)",min_value=0.0,value=4000.0,step=100.0)
            if st.form_submit_button("Ajouter le vitrage"):
                if nomv.strip():
                    vitrages.append({"id":uuid4().hex,"nom":nomv.strip(),"prix_m2":float(prixv),"actif":True})
                    save("vitrages",vitrages); st.success("Vitrage ajouté."); st.rerun()
                else: st.error("Le nom est obligatoire.")
        if vitrages: st.dataframe(pd.DataFrame(vitrages),use_container_width=True,hide_index=True)
        with st.expander("Modifier un prix de vitrage"):
            v = st.selectbox("Vitrage",vitrages,format_func=lambda x:x["nom"],key="edit_v")
            newv = st.number_input("Nouveau prix DA/m²",min_value=0.0,value=float(v["prix_m2"]),step=100.0)
            if st.button("Mettre à jour le prix vitrage"):
                for x in vitrages:
                    if x["id"]==v["id"]: x["prix_m2"]=float(newv)
                save("vitrages",vitrages); st.rerun()

elif page == "Accessoires":
    st.title("Catalogue des accessoires")
    with st.form("add_accessory"):
        a,b,c = st.columns(3)
        nom = a.text_input("Nom de l'accessoire")
        unite = b.selectbox("Unité",["pièce","paire","lot","mètre","autre"])
        prix = c.number_input("Prix unitaire (DA)",min_value=0.0,value=500.0,step=50.0)
        if st.form_submit_button("Ajouter l'accessoire"):
            if nom.strip():
                accessoires.append({"id":uuid4().hex,"nom":nom.strip(),"unite":unite,"prix_unitaire":float(prix),"actif":True})
                save("accessoires",accessoires); st.success("Accessoire ajouté."); st.rerun()
            else: st.error("Le nom est obligatoire.")
    if accessoires:
        st.dataframe(pd.DataFrame(accessoires),use_container_width=True,hide_index=True)
        with st.expander("Modifier un prix d'accessoire"):
            acc = st.selectbox("Accessoire",accessoires,format_func=lambda x:x["nom"])
            newprice = st.number_input("Nouveau prix",min_value=0.0,value=float(acc["prix_unitaire"]),step=50.0)
            if st.button("Mettre à jour le prix accessoire"):
                for x in accessoires:
                    if x["id"]==acc["id"]: x["prix_unitaire"]=float(newprice)
                save("accessoires",accessoires); st.rerun()

elif page == "Paramètres":
    st.title("Paramètres de l'entreprise")
    with st.form("settings_form"):
        nom = st.text_input("Nom de l'entreprise",params.get("entreprise_nom","Atelier PVC Pro"))
        adresse = st.text_input("Adresse",params.get("entreprise_adresse",""))
        telephone = st.text_input("Téléphone",params.get("entreprise_telephone",""))
        email = st.text_input("E-mail",params.get("entreprise_email",""))
        conditions = st.text_area("Conditions de paiement",params.get("conditions_paiement",""))
        validite = st.number_input("Validité du devis (jours)",min_value=1,max_value=365,value=int(params.get("validite_devis_jours",30)))
        tax_active = st.checkbox("Activer la taxe",value=bool(params.get("taxe_active",False)))
        taux = st.number_input("Taux de taxe (%)",min_value=0.0,max_value=100.0,value=float(params.get("taux_taxe",0)),step=0.5)
        regle = st.selectbox("Règle pour un vantail",["cadre_seul","cadre_et_ouvrant"],index=0 if params.get("regle_un_vantail","cadre_seul")=="cadre_seul" else 1,
                             format_func=lambda x:"Cadre seul (règle commerciale demandée)" if x=="cadre_seul" else "Cadre + ouvrant")
        prefixd = st.text_input("Préfixe devis",params.get("prefixe_devis","DEV"))
        prefixf = st.text_input("Préfixe facture",params.get("prefixe_facture","FAC"))
        if st.form_submit_button("Enregistrer les paramètres",type="primary"):
            params.update({"entreprise_nom":nom,"entreprise_adresse":adresse,"entreprise_telephone":telephone,
                           "entreprise_email":email,"conditions_paiement":conditions,"validite_devis_jours":int(validite),
                           "taxe_active":tax_active,"taux_taxe":float(taux),"regle_un_vantail":regle,
                           "prefixe_devis":prefixd.strip() or "DEV","prefixe_facture":prefixf.strip() or "FAC"})
            save("parametres",params); st.success("Paramètres enregistrés."); st.rerun()

elif page == "Sauvegarde":
    st.title("Sauvegarde et restauration")
    st.warning("Ne place jamais une sauvegarde contenant des données clients dans un dépôt GitHub public.")
    payload = store.export_all()
    st.download_button("Télécharger une sauvegarde JSON complète",
                       data=json.dumps(payload,ensure_ascii=False,indent=2).encode("utf-8"),
                       file_name=f"atelier_pvc_sauvegarde_{date.today().isoformat()}.json",
                       mime="application/json")
    uploaded = st.file_uploader("Restaurer une sauvegarde JSON",type=["json"])
    if uploaded:
        st.write("Fichier sélectionné :", uploaded.name)
        if st.button("⚠️ Restaurer cette sauvegarde",type="primary"):
            try:
                store.restore_all(json.loads(uploaded.getvalue().decode("utf-8")))
                st.success("Sauvegarde restaurée."); st.rerun()
            except Exception as exc:
                st.error(f"Restauration impossible : {exc}")
    st.subheader("Diagnostic")
    st.write("Backend :", "Supabase (persistant en ligne)" if store.remote else "JSON local (adapté aux tests locaux uniquement)")
    st.write("Collections :", ", ".join(COLLECTIONS))
