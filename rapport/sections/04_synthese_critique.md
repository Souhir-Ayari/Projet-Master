# Chapitre 3 — Synthèse critique

Le chapitre précédent a présenté six approches, chacune avec ses propres objectifs, données et méthodes. Ce chapitre les compare selon des critères communs, afin d'identifier ce que l'état de l'art permet déjà de faire, ce qu'il laisse de côté et les besoins auxquels une approche de recommandation de défenses contre les attaques visant les LLM doit répondre. Les jugements portés dans ce chapitre relèvent de notre analyse des articles ; lorsqu'une propriété n'est pas décrite dans un article, nous l'indiquons comme non rapportée.

## 3.1 Critères de comparaison

Les critères retenus découlent directement des difficultés identifiées dans la problématique. Ils permettent de situer chaque approche sur l'ensemble du chemin qui mène d'un texte de sécurité à une défense vérifiable :

- **la source des connaissances** : rapports CTI, articles scientifiques ou données construites par les auteurs ;
- **les attaques visées** : menaces informatiques classiques ou attaques propres aux LLM ;
- **le mode de construction des connaissances** : automatique ou manuel ;
- **la taxonomie de référence** : à quel référentiel les attaques sont rattachées ;
- **la défense produite** : l'approche propose-t-elle une mesure de protection ?
- **la vérification** : comment la sortie est-elle contrôlée, et par qui ?
- **la traçabilité** : peut-on retrouver la source sur laquelle repose chaque résultat ?
- **la mesure de la propagation des erreurs** : l'approche évalue-t-elle l'effet d'une erreur d'une étape sur les suivantes ?

## 3.2 Comparaison des approches

Le tableau 3.1 résume la position des six approches selon ces critères.

*Tableau 3.1 — Comparaison des approches de l'état de l'art (notre analyse ; n.r. : non rapporté)*

| Critère | CTINexus | LADDER | FALCON | TechniqueRAG | ATAG | Self-Refine |
|---|---|---|---|---|---|---|
| Source | Rapports CTI | Rapports CTI | CTI | Textes CTI | Articles et attaques implémentées | Non spécifique |
| Attaques visées | Menaces classiques | Menaces classiques | Réseau et système | Menaces classiques | Applications à agents LLM | Non spécifique |
| Construction | Automatique (LLM) | Automatique (BERT) | Automatique (LLM) | Automatique (RAG) | Manuelle | — |
| Taxonomie | Ontologie au choix | ATT&CK | n.r. | ATT&CK | ATLAS | — |
| Défense produite | Non | Non | Oui : règles Snort, YARA | Non | Non : évaluation des risques | Non |
| Vérification | n.r. | n.r. | Vérifications et auto-réflexion du modèle | n.r. | Raisonnement logique | Par le même modèle |
| Traçabilité vers la source | n.r. | n.r. | n.r. | n.r. | Enregistrements issus d'articles | Non |
| Propagation des erreurs mesurée | Non | Non | Non | Non | Non | Non |

Plusieurs constats se dégagent de ce tableau. Les approches les plus complètes en matière d'extraction, CTINexus et LADDER, s'arrêtent à la description des menaces. FALCON est la seule à produire une défense, mais elle repose en partie sur l'auto-évaluation du modèle et ne vise pas les attaques contre les LLM. TechniqueRAG et ATAG traitent chacune une étape essentielle, la classification et la constitution d'une base de connaissances, sans couvrir la chaîne complète. Enfin, aucune approche ne mesure comment une erreur commise à une étape se transmet aux suivantes.

## 3.3 Limites communes

L'analyse croisée fait apparaître cinq limites, qui correspondent aux difficultés posées dans la problématique.

### Des connaissances tirées de rapports CTI plutôt que de la littérature scientifique

Quatre des six approches exploitent des rapports CTI, qui décrivent des incidents ou des campagnes observés. Ces rapports sont précieux pour les menaces informatiques classiques, mais les attaques contre les LLM sont aujourd'hui surtout décrites dans des articles de recherche, qui présentent à la fois le mécanisme de l'attaque et, souvent, une défense évaluée. Seul ATAG s'appuie sur des articles, et il le fait manuellement.

### Une taxonomie inadaptée aux attaques contre les LLM

LADDER et TechniqueRAG rattachent les attaques à MITRE ATT&CK, qui ne couvre pas nativement l'injection de prompt ou le *jailbreak*. Seul ATAG utilise MITRE ATLAS, le référentiel dédié aux systèmes d'IA. Par ailleurs, les approches qui valident un identifiant vérifient qu'il appartient à la taxonomie, ce qui n'établit pas qu'il s'agit de la bonne technique ; TechniqueRAG obtient d'ailleurs des résultats nettement plus faibles sur les descriptions les moins standardisées.

### Une granularité limitée aux entités ou aux techniques

Les approches décrivent les attaques sous la forme d'entités et de relations (CTINexus), de schémas rattachés à une technique (LADDER, TechniqueRAG) ou de règles de détection (FALCON). Aucune ne décrit explicitement le déroulement de l'attaque en étapes successives, depuis le canal d'entrée jusqu'à son effet. Or c'est ce niveau de détail qui permet de choisir une défense agissant sur un point précis de l'attaque.

### Peu de défenses, et une vérification confiée au modèle

Une seule approche produit une défense, et sa qualité est contrôlée en partie par le modèle qui l'a générée. Les travaux sur l'auto-correction montrent que ce type de vérification est fragile, car un LLM tend à valider ses propres productions (Xu et al., 2024 ; Kamoi et al., 2024). Par ailleurs, aucune approche ne prévoit explicitement le cas où la littérature ne propose pas de défense : rien n'empêche alors le modèle d'en inventer une.

### Une traçabilité rarement assurée et des erreurs évaluées étape par étape

Hormis ATAG, dont les enregistrements proviennent d'articles identifiés, les approches ne permettent pas de retrouver la source précise sur laquelle repose chaque résultat. Surtout, toutes évaluent leurs étapes isolément : la qualité d'une classification, d'une extraction ou d'une règle. Aucune ne mesure ce que devient une erreur lorsqu'elle est réutilisée par l'étape suivante, alors que, dans un système qui enchaîne extraction, classification, recherche et génération, c'est cette propagation qui détermine la qualité de la recommandation finale. ATAG, en construisant sa base à la main, évite le coût de l'automatisation sans le mesurer.

## 3.4 Ce que l'état de l'art nous apporte

Ces limites ne remettent pas en cause l'intérêt des travaux étudiés. Chacun apporte une idée que notre approche réutilise :

- **CTINexus** montre qu'un LLM peut extraire des connaissances structurées d'un texte de sécurité sans réentraînement, et qu'il est utile de passer par des entités avant de construire une représentation plus riche ;
- **LADDER** confirme qu'il vaut mieux raisonner sur le mécanisme d'une attaque que sur des indicateurs isolés, et rattacher ce mécanisme à une taxonomie ;
- **FALCON** montre qu'il est possible de passer de la CTI à une défense concrète ;
- **TechniqueRAG** valide le principe consistant à restreindre les techniques proposées au modèle à une liste de candidats, puis à vérifier l'identifiant produit ;
- **ATAG** confirme l'intérêt d'une base de connaissances issue de la littérature et ancrée dans MITRE ATLAS ;
- **Self-Refine** apporte le cycle « proposer, vérifier, réviser » pour améliorer une réponse ;
- enfin, le **raisonnement à partir de cas** (Aamodt et Plaza, 1994), déjà combiné à la génération augmentée par la recherche dans CBR-RAG (Wiratunga et al., 2024), offre un cadre pour répondre à un nouveau problème à partir de cas documentés plutôt que par une génération libre.

## 3.5 Besoins identifiés

La confrontation de ces apports et de ces limites permet de formuler six besoins auxquels une approche de recommandation de défenses contre les attaques visant les LLM doit répondre :

- **B1 — Exploiter la littérature scientifique** : extraire automatiquement, à partir d'articles, les attaques contre les LLM, leur mécanisme et la défense proposée.
- **B2 — Ancrer chaque attaque dans une taxonomie adaptée** : rattacher chaque attaque à une technique MITRE ATLAS dont l'identifiant est vérifié, et enregistrer explicitement l'absence de défense lorsque l'article n'en propose pas.
- **B3 — Décrire l'attaque avec une granularité suffisante** : représenter son déroulement, depuis le canal d'entrée jusqu'à son effet, pour choisir une défense qui agit sur un point précis.
- **B4 — Produire une défense adaptée à l'attaque** : recommander une mesure fondée sur des cas documentés et adaptée à la nouvelle attaque, plutôt que générée librement.
- **B5 — Vérifier sans dépendre du modèle générateur et assurer la traçabilité** : contrôler chaque recommandation par un mécanisme extérieur au LLM et indiquer la source sur laquelle elle repose.
- **B6 — Mesurer la propagation des erreurs** : évaluer chaque étape sur les mêmes cas, en distinguant ce que le mécanisme vérifie de ce qu'il est censé garantir, et mesurer comment l'erreur d'une étape se transmet aux suivantes.

## 3.6 Conclusion

L'état de l'art fournit des composants solides : extraire des connaissances, classer une attaque, constituer une base de vulnérabilités, produire une défense ou corriger une réponse. Mais ces composants sont étudiés et évalués séparément, le plus souvent pour des menaces informatiques classiques, et aucun travail ne mesure ce qui se passe lorsqu'on les enchaîne pour protéger un système fondé sur un LLM. Les six besoins identifiés constituent le point de départ du chapitre suivant, qui présente notre positionnement, nos contributions et nos objectifs.
