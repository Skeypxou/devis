```python
import json, copy
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
.block-container{padding-top:1.5rem;max-width:1500px}
div[data-testid="stMetric"]{background:#fff;border:1px solid #e3eaf2;padding:16px;border-radius:12px}
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_store(): return Store()
store=get_store()
def load(n): return store.load(n)
def save(n,v): store.save(n,v)
def money(v): return f"{float(v):,.2f} DA".replace(","," ")
def next_number(items,prefix):
y=date.today().year
nums=[]
for it in items:
n=str(it.get("numero",""))
if n.startswith(f"{prefix}-{y}-"):
try: nums.append(int(n.rsplit("-",1)[1]))
except: pass
return f"{prefix}-{y}-{max(nums,default=0)+1:04d}"

params=load("parametres")
PAGES=["Tableau de bord","Clients","Nouveau devis","Devis et factures","Catalogue et tarifs","Accessoires","Paramètres","Sauvegarde"]
if "selected_page" not in st.session_state: st.session_state.selected_page=PAGES[0]

with st.sidebar:
st.markdown("# 🪟 Atelier PVC Pro")
st.caption("Devis · Factures · Gestion d'atelier")
page=st.radio("Navigation",PAGES,index=PAGES.index(st.session_state.selected_page))
st.session_state.selected_page=page
st.divider()
if store.remote: st.success("Stockage en ligne connecté")
else: st.warning("Stockage JSON local")

clients=load("clients"); devis=load("devis"); factures=load("factures")
paiements=load("paiements"); profiles=load("profiles_pvc"); vitrages=load("vitrages"); accessoires=load("accessoires")

def add_client(nom,telephone,email,adresse,ville):
if not nom.strip(): st.error("Nom obligatoire."); return
if any(c.get("nom","").strip().casefold()==nom.strip().casefold() and c.get("telephone","")==telephone for c in clients):
st.error("Client existe déjà."); return
clients.append({"id":uuid4().hex,"nom":nom.strip(),"telephone":telephone.strip(),"email":email.strip(),"adresse":adresse.strip(),"ville":ville.strip(),"date_creation":date.today().isoformat(),"actif":True})
save("clients",clients); st.success("Client enregistré.")

if page=="Tableau de bord":
st.title("Tableau de bord")
tf=sum(float(f.get("total_ttc",0)) for f in factures); tp=sum(float(p.get("montant",0)) for p in paiements)
c1,c2,c3,c4=st.columns(4)
c1.metric("Clients",len(clients)); c2.metric("Devis",len(devis)); c3.metric("Total facturé",money(tf)); c4.metric("Reste",money(max(tf-tp,0)))
st.subheader("Derniers devis")
if devis: st.dataframe(pd.DataFrame(devis).sort_values("date",ascending=False).head(8),use_container_width=True,hide_index=True)
else: st.info("Aucun devis.")

elif page=="Clients":
st.title("Clients")
with st.expander("➕ Ajouter un client",expanded=not clients):
with st.form("client_form",clear_on_submit=True):
a,b=st.columns(2)
nom=a.text_input("Nom "); tel=b.text_input("Téléphone"); email=a.text_input("E-mail"); ville=b.text_input("Ville"); adresse=st.text_area("Adresse")
if st.form_submit_button("Enregistrer",type="primary"): add_client(nom,tel,email,adresse,ville); st.rerun()
search=st.text_input("Rechercher")
filt=[c for c in clients if search.casefold() in " ".join(str(c.get(k,"")) for k in ("nom","telephone","ville")).casefold()]
if filt:
st.dataframe(pd.DataFrame(filt),use_container_width=True,hide_index=True)
with st.expander("Modifier / Archiver"):
sel=st.selectbox("Client",filt,format_func=lambda x:f"{x['nom']} — {x.get('telephone','')}")
with st.form("edit_client"):
n=st.text_input("Nom",sel.get("nom","")); t=st.text_input("Téléphone",sel.get("telephone","")); e=st.text_input("E-mail",sel.get("email","")); ad=st.text_input("Adresse",sel.get("adresse","")); v=st.text_input("Ville",sel.get("ville","")); act=st.checkbox("Actif",value=sel.get("actif",True))
if st.form_submit_button("Enregistrer"):
for c in clients:
if c["id"]==sel["id"]: c.update({"nom":n.strip(),"telephone":t.strip(),"email":e.strip(),"adresse":ad.strip(),"ville":v.strip(),"actif":act})
save("clients",clients); st.success("Mis à jour"); st.rerun()

elif page=="Nouveau devis":
st.title("Créer un devis global")
st.caption("1 client = 1 devis. Le 1er produit s'additionne au 2ème, au 3ème... Un seul total et un seul PDF.")
if not clients: st.warning("Ajoute d'abord un client.")
else:
if "lignes_devis_cours" not in st.session_state: st.session_state.lignes_devis_cours=[]
if "edit_ligne_id" not in st.session_state: st.session_state.edit_ligne_id=None
if "devis_client_id" not in st.session_state: st.session_state.devis_client_id=None
if "editing_existing_devis_id" not in st.session_state: st.session_state.editing_existing_devis_id=None

if st.session_state.editing_existing_devis_id:
d_edit=next((d for d in devis if d["id"]==st.session_state.editing_existing_devis_id),None)
if d_edit: st.warning(f"✏️ MODE MODIFICATION : Devis {d_edit['numero']} — {d_edit['client_nom']} — modifie les lignes puis enregistre pour mettre à jour.")
if st.button("Annuler la modification et revenir en création"):
st.session_state.editing_existing_devis_id=None; st.session_state.lignes_devis_cours=[]; st.session_state.edit_ligne_id=None; st.rerun()

actifs=[c for c in clients if c.get("actif",True)]
# si modification, force le client du devis
default_idx=0
if st.session_state.editing_existing_devis_id:
d_edit=next((d for d in devis if d["id"]==st.session_state.editing_existing_devis_id),None)
if d_edit:
ids=[c["id"] for c in actifs]
if d_edit["client_id"] in ids: default_idx=ids.index(d_edit["client_id"])
client=st.selectbox("Client ",actifs,index=default_idx,format_func=lambda c:f"{c['nom']} — {c.get('telephone','')}")

if st.session_state.devis_client_id is None: st.session_state.devis_client_id=client["id"]
if st.session_state.lignes_devis_cours and st.session_state.devis_client_id!=client["id"] and not st.session_state.editing_existing_devis_id:
st.warning(f"Panier en cours pour un autre client ({len(st.session_state.lignes_devis_cours)} lignes).")
c1,c2=st.columns(2)
if c1.button("🗑️ Vider et changer"): st.session_state.lignes_devis_cours=[]; st.session_state.edit_ligne_id=None; st.session_state.devis_client_id=client["id"]; st.rerun()
if c2.button("Annuler"): st.rerun()
st.stop()
st.session_state.devis_client_id=client["id"]

edit_data=next((l for l in st.session_state.lignes_devis_cours if l.get("ligne_id")==st.session_state.edit_ligne_id),None) if st.session_state.edit_ligne_id else None
if edit_data: st.info(f"✏️ Modification ligne : {edit_data['designation']}")
def get_def(k,d): return edit_data.get(k,d) if edit_data else d

st.subheader("Ajouter une menuiserie / rideau")
with st.container(border=True):
a,b,c=st.columns(3)
cats=["Fenêtre","Porte-fenêtre","Baie vitrée","Rideau manuel","Rideau motorisé","Porte PVC","Imposte"]
cat_def=get_def("categorie","Fenêtre")
cat= a.selectbox("Type",cats,index=cats.index(cat_def) if cat_def in cats else 0)
des_raw=get_def("designation","Menuiserie PVC")
if edit_data and " — " in des_raw: des_raw=des_raw.split(" — ",1)[1]
des=b.text_input("Désignation",value=des_raw)
qte=c.number_input("Quantité",1,1000,int(get_def("quantite",1)),1)
a,b,c=st.columns(3)
larg=a.number_input("Largeur (m)",0.01,20.0,float(get_def("largeur",1.20)),0.05,format="%.2f")
haut=b.number_input("Hauteur (m)",0.01,20.0,float(get_def("hauteur",1.40)),0.05,format="%.2f")
est_rideau=cat in ("Rideau manuel","Rideau motorisé")
vant=1; ouv="Non applicable"; vit={"nom":"Non applicable","prix_m2":0}; prof={"nom":"Rideau","prix_ml":0}; prix_ml=0.0; prix_m2=0.0; mode="Surface brute"; lv=larg; hv=haut; nbv=1; extra=0.0
prix_rideau=float(get_def("prix_rideau_m2",6000.0))
if est_rideau:
prix_rideau=st.number_input("Prix rideau (DA/m²)",0.0,1000000.0,prix_rideau,100.0,key="prideau")
su=larghaut; stot=suint(qte)
st.success(f"Surface unitaire: {su:.2f} m² | Prix unitaire: {money(suprix_rideau)} | Total ligne: {money(stotprix_rideau)}")
else:
vant=c.number_input("Vantaux",1,12,int(get_def("nb_vantaux",2)),1)
a,b,c=st.columns(3)
ouv_opts=["Coulissant","Ouverture simple","Oscillo-battant","Autre"]
ov=get_def("ouverture","Coulissant")
ouv=a.selectbox("Ouverture",ouv_opts,index=ouv_opts.index(ov) if ov in ouv_opts else 0)
vit=b.selectbox("Vitrage",vitrages,format_func=lambda x:x["nom"])
prof=c.selectbox("Profilé",profiles,format_func=lambda x:f"{x['nom']} ({money(x['prix_ml'])}/ml)")
a,b,c=st.columns(3)
prix_ml=a.number_input("Prix PVC (DA/ml)",0.0,1000000.0,float(prof.get("prix_ml",6000)),100.0)
prix_m2=b.number_input("Prix vitrage (DA/m²)",0.0,1000000.0,float(vit.get("prix_m2",2500)),100.0)
mode_opts=["Surface brute","Dimensions réelles - manuel","Dimensions réelles - automatique"]
mv=get_def("mode_vitrage","Surface brute")
mode=c.selectbox("Mode vitrage",mode_opts,index=mode_opts.index(mv) if mv in mode_opts else 0)
if mode=="Dimensions réelles - manuel":
a,b,c=st.columns(3)
lv=a.number_input("Largeur verre (m)",0.001,20.0,float(get_def("largeur_v",1.10)),0.01,format="%.3f")
hv=b.number_input("Hauteur verre (m)",0.001,20.0,float(get_def("hauteur_v",1.30)),0.01,format="%.3f")
nbv=c.number_input("Nb vitrages",1,20,int(get_def("nb_vitrages",vant)),1)
elif mode=="Dimensions réelles - automatique":
a,b,c=st.columns(3)
nbv=a.number_input("Nb vitrages",1,20,int(get_def("nb_vitrages",vant)),1)
dl=b.number_input("Déduction larg (mm)",0.0,1000.0,100.0,5.0); dh=c.number_input("Déduction haut (mm)",0.0,1000.0,100.0,5.0)
lv=larg/int(nbv)-dl/1000; hv=haut-dh/1000
if lv>0 and hv>0: st.info(f"Verre: {lv:.3f} x {hv:.3f} m")
else: st.error("Déductions trop grandes")
else: lv,hv,nbv=larg,haut,1
st.markdown("Accessoires")
choix=st.multiselect("Accessoires",accessoires,format_func=lambda x:f"{x['nom']} — {money(x['prix_unitaire'])}")
qte_acc={}
for acc in choix: qte_acc[acc["id"]]=st.number_input(f"Qté / unité : {acc['nom']}",0,100,1,key=f"acc_{acc['id']}")
a,b,c=st.columns(3)
autres=a.number_input("Pose (DA)",0.0,10000000.0,float(get_def("autres_couts",params.get("frais_pose_par_defaut",0))),500.0)
remise=b.number_input("Remise (DA)",0.0,10000000.0,float(get_def("remise",0.0)),100.0)
if not est_rideau: extra=c.number_input("Profilé supp (ml/u)",0.0,100.0,float(get_def("profil_extra",0.0)),0.1)
col_add,col_cancel=st.columns([3,1])
label="✅ Mettre à jour" if st.session_state.edit_ligne_id else "➕ Ajouter au devis (s'additionne)"
if col_add.button(label,type="primary",use_container_width=True):
try:
if larg<=0 or haut<=0: st.error("Dimensions >0"); st.stop()
if not est_rideau and (lv<=0 or hv<=0): st.error("Dimensions verre >0"); st.stop()
if est_rideau:
su=larghaut; stot=suint(qte); cout_rideau=stotfloat(prix_rideau)
metrage={"ml_total":0.0,"ml_total_unitaire":0.0,"ml_cadre":0.0,"ml_horizontaux_ouvrants":0.0,"ml_verticaux_ouvrants":0.0,"cout_pvc_total":0.0}
surf={"surface_totale":stot}; cout_vit=cout_rideau
else:
metrage=calculer_metrage_pvc(larg,haut,int(vant),float(prix_ml),int(qte),params.get("regle_un_vantail","cadre_seul"),float(extra))
surf=calculer_surface_vitrage(larg,haut,int(qte),"dimensions_reelles" if mode!="Surface brute" else "brute",float(lv),float(hv),int(nbv))
cout_vit=surf["surface_totale"]float(prix_m2); cout_rideau=0.0; su=0.0; stot=0.0
cout_acc=sum(float(a["prix_unitaire"])qte_acc.get(a["id"],0) for a in choix)int(qte)
tot=calculer_total(metrage["cout_pvc_total"],cout_vit,cout_acc,float(autres),float(remise),params.get("taxe_active",False),params.get("taux_taxe",0))
pu=tot["total_ttc"]/int(qte) if int(qte)>0 else tot["total_ttc"]
ligne={"ligne_id":st.session_state.edit_ligne_id if st.session_state.edit_ligne_id else uuid4().hex,"designation":f"{cat} — {des}","categorie":cat,"largeur":float(larg),"hauteur":float(haut),"quantite":int(qte),"nb_vantaux":int(vant) if not est_rideau else 1,"ouverture":ouv,"vitrage":vit["nom"],"surface_vitrage":0.0 if est_rideau else float(surf["surface_totale"]),"prix_vitrage_m2":float(prix_m2),"type_tarification":"surface_m2" if est_rideau else "vitrage","surface_rideau":float(surf["surface_totale"]) if est_rideau else 0.0,"surface_rideau_unitaire":float(su) if est_rideau else 0.0,"prix_rideau_m2":float(prix_rideau) if est_rideau else 0.0,"cout_rideau":round(float(cout_rideau),2),"ml_total":float(metrage["ml_total"]),"ml_unitaire":float(metrage["ml_total_unitaire"]),"cout_pvc":float(metrage["cout_pvc_total"]),"cout_vitrage":round(float(cout_vit),2),"cout_accessoires":round(float(cout_acc),2),"accessoires":[{"nom":a["nom"],"quantite_par_unite":qte_acc[a["id"]],"prix_unitaire":a["prix_unitaire"]} for a in choix],"autres_couts":float(autres),"remise":float(remise),"total_ligne":float(tot["total_ttc"]),"total_ht_ligne":float(tot["total_ht"]),"taxe_ligne":float(tot["taxe"]),"prix_unitaire":round(float(pu),2),"details_metrage":metrage,"mode_vitrage":mode,"largeur_v":float(lv),"hauteur_v":float(hv),"nb_vitrages":int(nbv),"profil_extra":float(extra)}
if st.session_state.edit_ligne_id:
for i,l in enumerate(st.session_state.lignes_devis_cours):
if l.get("ligne_id")==st.session_state.edit_ligne_id: st.session_state.lignes_devis_cours[i]=ligne; break
st.session_state.edit_ligne_id=None; st.success("Ligne mise à jour")
else: st.session_state.lignes_devis_cours.append(ligne); st.success(f"Ajouté : {ligne['designation']} — {money(ligne['total_ligne'])}")
st.rerun()
except Exception as e: st.error(f"Erreur: {e}")
if st.session_state.edit_ligne_id and col_cancel.button("Annuler",use_container_width=True):
st.session_state.edit_ligne_id=None; st.rerun()

if st.session_state.lignes_devis_cours:
st.divider()
st.subheader(f"Récapitulatif ({len(st.session_state.lignes_devis_cours)} produits) — tout s'additionne")
rows=[]
for i,l in enumerate(st.session_state.lignes_devis_cours,1):
rows.append({"N°":i,"Désignation":l["designation"],"Type":l["categorie"],"Dimensions":f"{l['largeur']:.2f}x{l['hauteur']:.2f} m","Qté":l["quantite"],"ML PVC":f"{l['ml_total']:.2f}" if l['ml_total']>0 else "—","Surf vitrage":f"{l['surface_vitrage']:.2f}" if l['surface_vitrage']>0 else "—","Surf rideau":f"{l['surface_rideau']:.2f}" if l['surface_rideau']>0 else "—","PU":money(l["prix_unitaire"]),"Total":money(l["total_ligne"])})
st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
total_gen=sum(float(l["total_ligne"]) for l in st.session_state.lignes_devis_cours)
a,b,c=st.columns(3); a.metric("Lignes",len(st.session_state.lignes_devis_cours)); b.metric("TOTAL GÉNÉRAL",money(total_gen)); c.metric("Client",client["nom"])
st.markdown("Gérer les lignes :")
for l in st.session_state.lignes_devis_cours:
c1,c2,c3=st.columns([6,2,2])
c1.write(f"{l['designation']} {l['largeur']:.2f}x{l['hauteur']:.2f} x{l['quantite']} = {money(l['total_ligne'])}")
if c2.button("✏️",key=f"edit_{l['ligne_id']}"): st.session_state.edit_ligne_id=l["ligne_id"]; st.rerun()
if c3.button("🗑️",key=f"del_{l['ligne_id']}"):
st.session_state.lignes_devis_cours=[x for x in st.session_state.lignes_devis_cours if x["ligne_id"]!=l["ligne_id"]]
if st.session_state.edit_ligne_id==l["ligne_id"]: st.session_state.edit_ligne_id=None
st.rerun()
st.divider()
obs=st.text_area("Observations globales",value=st.session_state.get("observations_globales",""))
st.session_state.observations_globales=obs
c1,c2=st.columns(2)
if c1.button("🧹 Vider tout",use_container_width=True): st.session_state.lignes_devis_cours=[]; st.session_state.edit_ligne_id=None; st.rerun()
is_edit=st.session_state.editing_existing_devis_id is not None
if c2.button("💾 Mettre à jour le devis" if is_edit else "💾 Enregistrer le devis global (1 numéro)",type="primary",use_container_width=True):
if not st.session_state.lignes_devis_cours: st.error("Ajoute au moins 1 produit"); st.stop()
th=sum(float(l.get("total_ht_ligne",l["total_ligne"])) for l in st.session_state.lignes_devis_cours)
tx=sum(float(l.get("taxe_ligne",0)) for l in st.session_state.lignes_devis_cours)
ttc=sum(float(l["total_ligne"]) for l in st.session_state.lignes_devis_cours)
if is_edit:
for d in devis:
if d["id"]==st.session_state.editing_existing_devis_id:
d.update({"client_id":client["id"],"client_nom":client["nom"],"client_telephone":client.get("telephone",""),"lignes":copy.deepcopy(st.session_state.lignes_devis_cours),"total_ht":round(th,2),"taxe":round(tx,2),"total_ttc":round(ttc,2),"observations":obs})
save("devis",devis); st.success(f"Devis {d['numero']} mis à jour — {money(ttc)}")
pdf=generer_pdf(d,params,"DEVIS"); st.download_button("📄 Télécharger PDF",pdf,file_name=f"{d['numero']}.pdf",mime="application/pdf")
break
st.session_state.editing_existing_devis_id=None
else:
doc={"id":uuid4().hex,"numero":next_number(devis,params.get("prefixe_devis","DEV")),"date":date.today().isoformat(),"client_id":client["id"],"client_nom":client["nom"],"client_telephone":client.get("telephone",""),"lignes":copy.deepcopy(st.session_state.lignes_devis_cours),"total_ht":round(th,2),"taxe":round(tx,2),"total_ttc":round(ttc,2),"statut":"Brouillon","observations":obs,"conditions":params.get("conditions_paiement",""),"type":"devis"}
devis.append(doc); save("devis",devis)
st.success(f"Devis global {doc['numero']} enregistré : {len(doc['lignes'])} produits — {money(ttc)}")
pdf=generer_pdf(doc,params,"DEVIS"); st.download_button("📄 Télécharger PDF unique",pdf,file_name=f"{doc['numero']}.pdf",mime="application/pdf")
if st.button("Nouveau panier"): st.session_state.lignes_devis_cours=[]; st.session_state.edit_ligne_id=None; st.session_state.observations_globales=""; st.session_state.editing_existing_devis_id=None; st.rerun()
else: st.info("Aucun produit. Remplis le formulaire et clique sur Ajouter —
