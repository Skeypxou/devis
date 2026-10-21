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
st.write(f"Bienvenue dans {params.get('entreprise_nom','Atelier PVC Pro')}.")
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
nom = a.text_input("Nom ou raison sociale ")
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
st.caption("Sélectionnez un client, ajoutez autant de produits que nécessaire (fenêtres, portes, impostes, baies, rideaux), puis enregistrez un seul devis avec un seul PDF.")

if not clients:
st.warning("Ajoute d'abord un client dans la rubrique Clients.")
else:
# --- Session State pour le panier ---
if "lignes_devis_cours" not in st.session_state:
st.session_state.lignes_devis_cours = []
if "edit_ligne_id" not in st.session_state:
st.session_state.edit_ligne_id = None
if "devis_client_id" not in st.session_state:
st.session_state.devis_client_id = None
if "observations_globales" not in st.session_state:
st.session_state.observations_globales = ""

actifs = [c for c in clients if c.get("actif", True)]
client = st.selectbox("Client ", actifs, format_func=lambda c: f"{c['nom']} — {c.get('telephone','')}")

# Cohérence client / panier
if st.session_state.lignes_devis_cours and st.session_state.devis_client_id and st.session_state.devis_client_id != client["id"]:
st.warning(f"Un devis est en cours pour un autre client ({len(st.session_state.lignes_devis_cours)} ligne(s)). Changez de client videra le panier en cours.")
if st.button("🗑️ Vider le panier et changer de client", type="secondary"):
st.session_state.lignes_devis_cours = []
st.session_state.edit_ligne_id = None
st.session_state.devis_client_id = client["id"]
st.session_state.observations_globales = ""
st.rerun()
else:
st.session_state.devis_client_id = client["id"]

# --- Mode édition : pré-remplissage ---
edit_data = None
if st.session_state.edit_ligne_id:
edit_data = next((l for l in st.session_state.lignes_devis_cours if l.get("ligne_id") == st.session_state.edit_ligne_id), None)
if edit_data:
st.info(f"✏️ Modification en cours : {edit_data['designation']} — modifiez les champs puis cliquez sur Mettre à jour*.")

st.subheader("Ajouter une menuiserie / rideau")
with st.container(border=True):
# Valeurs par défaut (ajout ou édition)
def get_def(key, default):
return edit_data.get(key, default) if edit_data else default

a,b,c = st.columns(3)
# On garde l'ordre demandé : Fenêtre, Porte-fenêtre, Baie vitrée, Rideau manuel, Rideau motorisé, Porte PVC, Imposte
categories = ["Fenêtre","Porte-fenêtre","Baie vitrée","Rideau manuel","Rideau motorisé","Porte PVC","Imposte"]
cat_default = get_def("categorie", "Fenêtre")
cat_index = categories.index(cat_default) if cat_default in categories else 0
categorie = a.selectbox("Type de produit", categories, index=cat_index)
designation = b.text_input("Désignation", value=get_def("designation", "Menuiserie PVC").replace(f"{cat_default} — ","") if edit_data else "Menuiserie PVC")
# Si édition, la désignation stockée est "Catégorie — Désignation", on extrait
if edit_data and " — " in edit_data.get("designation",""):
designation_val = edit_data["designation"].split(" — ",1)[1]
# forcer l'affichage ( workaround : on réaffecte via key)
# Streamlit ne permet pas de changer value dynamiquement sans key, on utilise la valeur initiale ci-dessus
pass

quantite = c.number_input("Quantité", min_value=1, max_value=1000, value=int(get_def("quantite",1)), step=1)

a,b,c = st.columns(3)
largeur = a.number_input("Largeur (m)", min_value=0.01, max_value
