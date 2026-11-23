# Page de garde

---

**MÉMOIRE** présenté en vue de l'obtention du **Diplôme de Mastère de Recherche en Informatique**

Parcours : Smart Systems & IoT

**Sujet : Nexus Intel : De la Publication à la Protection — Synthèse Automatisée des Défenses contre les Menaces Émergentes sur les LLM**

Élaboré par : **Souhir AYARI** · Laboratoire LARIA · ENSI, Université de la Manouba

Encadrante : Dr Amal TARIFA, Maître Assistante · Année universitaire 2025/2026

---

# Table des matières

---

- Introduction générale
- Chapitre 1 — Problématique
  - 1.1 Du constat au problème
  - 1.2 Les difficultés à surmonter
    - Extraire des connaissances fiables à partir d'articles hétérogènes
    - Ancrer chaque attaque dans une taxonomie adaptée
    - Décrire l'attaque avec une granularité suffisante
    - Maîtriser les hallucinations et vérifier les recommandations
  - 1.3 Question de recherche
  - 1.4 Conclusion
- Chapitre 2 — État de l'art
  - 2.1 CTINexus : construction de graphes de connaissances CTI par apprentissage en contexte
    - Principe
    - Méthodologie et techniques utilisées
    - Contributions et résultats
    - Limites
    - Relation avec notre travail
  - 2.2 LADDER : extraction de schémas d'attaque reliés à MITRE ATT&CK
    - Principe
    - Méthodologie et techniques utilisées
    - Contributions et résultats
    - Limites
    - Relation avec notre travail
  - 2.3 FALCON : génération de règles de détection à partir de la CTI
    - Principe
    - Méthodologie et techniques utilisées
    - Contributions et résultats
    - Limites
    - Relation avec notre travail
  - 2.4 TechniqueRAG : classification des techniques d'attaque par génération augmentée
    - Principe
    - Méthodologie et techniques utilisées
    - Contributions et résultats
    - Limites
    - Relation avec notre travail
  - 2.5 ATAG : graphes d'attaque et base de vulnérabilités des LLM
    - Principe
    - Méthodologie et techniques utilisées
    - Contributions et résultats
    - Limites
    - Relation avec notre travail
  - 2.6 Self-Refine : amélioration itérative par auto-évaluation
    - Principe
    - Méthodologie et techniques utilisées
    - Contributions et résultats
    - Limites
    - Relation avec notre travail
  - 2.7 Autres travaux connexes
  - 2.8 Conclusion
- Références bibliographiques

---

# Liste des figures

---

*(aucune figure pour l'instant)*

---

# Liste des tableaux

---

*(aucun tableau pour l'instant)*

---

# Liste des acronymes

---

| Sigle | Signification |
|---|---|
| **ATLAS** | *Adversarial Threat Landscape for Artificial-Intelligence Systems* (MITRE), base de connaissances des techniques d'attaque visant les systèmes d'IA |
| **ATT&CK** | *Adversarial Tactics, Techniques, and Common Knowledge* (MITRE), base de connaissances des techniques d'attaque informatiques |
| **BERT** | *Bidirectional Encoder Representations from Transformers*, famille de modèles de langage encodeurs |
| **CARL** | *Case-based Attack Remediation for LLMs*, l'approche proposée dans ce mémoire |
| **CBR** | *Case-Based Reasoning*, raisonnement à partir de cas : retrouver un cas passé similaire, réutiliser sa solution, la réviser et la conserver |
| **CTI** | *Cyber Threat Intelligence*, renseignement sur les menaces : rapports qui décrivent les menaces et les attaques observées |
| **IA** | Intelligence artificielle |
| **IDS** | *Intrusion Detection System*, système de détection d'intrusion |
| **IoC** | *Indicator of Compromise*, indicateur de compromission (adresse IP, nom de domaine, empreinte de fichier…) |
| **LLM** | *Large Language Model*, grand modèle de langage |
| **LVD** | *LLM Vulnerability Database*, base de vulnérabilités des LLM introduite avec ATAG |
| **RAG** | *Retrieval-Augmented Generation*, génération augmentée par la recherche : le modèle répond à partir de documents retrouvés plutôt que de sa seule mémoire |

---

# Introduction générale

Au cours des dernières années, les progrès réalisés dans le domaine de l’intelligence artificielle (IA) ont favorisé l’émergence de modèles de langage de grande taille (*Large Language Models — LLM*), capables de comprendre, de traiter et de générer du texte en langage naturel avec des performances de plus en plus avancées. Ces modèles occupent aujourd’hui une place croissante dans le développement des applications intelligentes, notamment à travers les assistants conversationnels, les agents autonomes, les systèmes d’aide à la décision et les applications intégrant des capacités de génération et d’analyse de contenu. Leur adoption s’explique notamment par leur capacité à faciliter l’interaction entre les utilisateurs et les systèmes informatiques, à automatiser certaines tâches complexes et à exploiter de grandes quantités d’informations pour produire des réponses adaptées à différents contextes. Cependant, cette évolution s’accompagne de nouveaux enjeux en matière de sécurité, particulièrement lorsque ces modèles sont intégrés dans des applications accessibles aux utilisateurs ou connectés à des ressources externes.

L’utilisation croissante des LLM élargit en effet la surface d’attaque des systèmes informatiques et introduit des vulnérabilités qui ne se limitent pas aux mécanismes traditionnels de sécurité. Contrairement aux logiciels classiques, les modèles de langage interprètent des instructions, manipulent du contenu textuel et interagissent avec des données dont la nature et la fiabilité peuvent varier. Cette particularité peut être exploitée par des acteurs malveillants afin de détourner le comportement du modèle, de contourner ses mécanismes de sécurité ou de compromettre les applications qui l’utilisent. Parmi les principales menaces identifiées dans ce domaine figurent notamment la *Prompt Injection*, qui consiste à introduire des instructions malveillantes dans les entrées ou les contenus traités par le modèle afin de modifier son comportement (MITRE ATLAS, technique AML.T0051 « LLM Prompt Injection » ; Greshake et al., 2023), le *Jailbreak*, qui vise à contourner les restrictions et les mécanismes de sécurité imposés au modèle (MITRE ATLAS, technique AML.T0054 « LLM Jailbreak » ; Wei et al., 2023), ainsi que le *Data Poisoning*, qui repose sur la manipulation des données utilisées dans les processus d’entraînement ou d’adaptation afin d’influencer les résultats du système (MITRE ATLAS, technique AML.T0020 « Poison Training Data » ; Carlini et al., 2024). Ces attaques peuvent affecter la fiabilité des réponses générées, compromettre la confidentialité des informations ou conduire à des comportements non souhaités dans les applications intégrant des LLM.

Face à ces menaces émergentes, de nombreux travaux scientifiques proposent des mécanismes de détection, de prévention et de mitigation destinés à renforcer la sécurité des modèles de langage et de leurs applications. Ces recherches explorent différentes stratégies, allant de la conception de mécanismes de filtrage des entrées et des sorties à l'amélioration des processus d'entraînement, en passant par l'utilisation de techniques de détection, de validation et de contrôle des comportements du modèle. Ainsi, la littérature scientifique constitue une source importante de connaissances permettant de comprendre les mécanismes des attaques, d'identifier leurs conditions d'exploitation et d'étudier les solutions de défense proposées. Néanmoins, la multiplication rapide des publications scientifiques, la diversité des types d'attaques et l'évolution constante des techniques adversariales rendent difficile l'exploitation efficace de ces connaissances.

Les informations relatives aux attaques contre les LLM et aux solutions de défense sont généralement présentées dans des articles scientifiques distincts, avec des niveaux de détail, des terminologies et des structures variables. Certaines publications décrivent précisément le mécanisme d'une attaque et ses conséquences, tandis que d'autres se concentrent davantage sur l'évaluation d'une méthode de défense ou sur la présentation d'un nouveau mécanisme de protection. Cette dispersion des connaissances complique leur identification, leur comparaison et leur réutilisation dans un contexte opérationnel. La recherche manuelle dans un ensemble important de publications devient alors une tâche coûteuse en temps, nécessitant une lecture approfondie, une analyse critique et une synthèse des informations pertinentes. Elle peut également rendre difficile le suivi des nouvelles menaces et l'identification des défenses les plus adaptées à une attaque donnée.

L'exploitation de cette littérature à l'aide de méthodes automatisées représente ainsi une perspective intéressante pour améliorer l'accès aux connaissances en cybersécurité. Les techniques de traitement automatique du langage naturel et les modèles de langage offrent la possibilité d'analyser des documents scientifiques, d'extraire les informations pertinentes et de faciliter leur organisation et leur exploitation. Toutefois, leur utilisation dans ce contexte doit être accompagnée d'une attention particulière à la fiabilité des résultats générés. En effet, les modèles de langage peuvent produire des informations incorrectes, interpréter de manière imprécise les mécanismes d'une attaque, omettre des éléments importants ou générer des recommandations qui ne sont pas suffisamment adaptées au contexte étudié. La production d'une réponse plausible ne garantit donc pas nécessairement sa pertinence ni sa validité du point de vue de la cybersécurité. Il devient essentiel de disposer de mécanismes permettant de relier les recommandations produites aux connaissances scientifiques qui les justifient, tout en assurant leur cohérence et leur vérifiabilité.

Dans ce contexte, ce mémoire s'inscrit dans la perspective de transformer les connaissances scientifiques dispersées sur les menaces visant les modèles de langage en informations exploitables pour la compréhension des attaques et l'identification de mesures de défense adaptées. L'enjeu ne consiste pas uniquement à extraire des informations depuis des publications scientifiques, mais également à structurer ces connaissances, à préserver leur contexte et à faciliter leur réutilisation lors de l'analyse de nouvelles menaces. Une telle démarche vise à rapprocher les connaissances issues de la recherche scientifique des besoins liés à la cybersécurité, en favorisant une exploitation plus organisée, contextualisée et fiable des informations disponibles.

Le travail proposé, intitulé **Nexus Intel : De la Publication à la Protection — Synthèse Automatisée des Défenses contre les Menaces Émergentes sur les LLM**, s'inscrit dans cette orientation. Il vise à explorer une approche permettant de valoriser la littérature scientifique afin de faciliter l'analyse des attaques contre les modèles de langage et de soutenir la formulation de recommandations de défense pertinentes, précises et vérifiables. Cette démarche cherche ainsi à contribuer à une meilleure exploitation des connaissances scientifiques en cybersécurité, en réduisant les difficultés liées à leur dispersion et en accordant une attention particulière à la fiabilité des informations utilisées pour proposer des solutions de protection.

---

# Chapitre 1 — Problématique

L'introduction a présenté le contexte général de ce travail : l'essor des modèles de langage, les attaques qui les visent et l'abondance des travaux scientifiques consacrés à leur défense. Ce chapitre précise le problème auquel nous nous intéressons, les difficultés qu'il soulève et la question de recherche qui guide la suite de ce mémoire.

## 1.1 Du constat au problème

Lorsqu'une nouvelle attaque contre un système fondé sur un LLM est signalée, il est rare qu'elle soit entièrement inédite. Le plus souvent, une attaque comparable, ou une variante proche, a déjà été décrite dans un article, avec son mode opératoire et, parfois, une contre-mesure. La connaissance nécessaire pour se défendre existe donc ; ce qui manque, c'est un moyen fiable de la retrouver et de la transformer en une recommandation applicable à la situation présente.

Le problème que nous étudions est donc celui du passage de la publication à la protection : à partir d'un ensemble d'articles scientifiques sur les attaques contre les LLM, il s'agit de produire, pour une attaque donnée, une recommandation de défense qui soit fondée sur ces articles. Cette recommandation doit être précise, c'est-à-dire viser le mécanisme réel de l'attaque ; contextualisée, c'est-à-dire adaptée à l'attaque étudiée plutôt que copiée d'un cas différent ; et vérifiable, c'est-à-dire accompagnée de la source sur laquelle elle s'appuie, afin qu'un analyste puisse la contrôler avant de l'appliquer.

Confier directement cette tâche à un modèle de langage n'est pas satisfaisant. Un LLM interrogé sur une attaque produit volontiers une réponse fluide et générale, mais rien ne garantit qu'elle provienne d'une source identifiable : le modèle peut s'appuyer sur ses connaissances internes, les combiner de manière inexacte ou inventer une mesure plausible. Ce phénomène d'hallucination est aujourd'hui bien documenté, au point que des corpus entiers sont construits pour l'étudier dans les systèmes de génération augmentée par la recherche (Niu et al., 2024). Dans un contexte de sécurité, une recommandation de ce type est particulièrement problématique, car elle peut être appliquée avec une confiance qu'elle ne mérite pas.

## 1.2 Les difficultés à surmonter

Exploiter la littérature pour recommander des défenses soulève plusieurs difficultés, qui interviennent à des étapes différentes du traitement.

### Extraire des connaissances fiables à partir d'articles hétérogènes

Les articles scientifiques ne sont pas rédigés pour être exploités automatiquement. Une même section peut mêler la description d'une attaque, les résultats d'une expérience et la présentation d'une défense, avec des terminologies qui varient d'un auteur à l'autre. Il faut donc identifier, dans un texte long et peu structuré, les passages qui décrivent réellement une attaque, puis en extraire le mécanisme et la défense proposée. Une difficulté supplémentaire tient au fait que tous les articles ne proposent pas de défense : dans ce cas, le système doit enregistrer cette absence, plutôt que de la combler par une mesure inventée.

### Ancrer chaque attaque dans une taxonomie adaptée

Pour comparer des attaques issues d'articles différents, il est nécessaire de les rattacher à un référentiel commun. Le référentiel le plus utilisé en renseignement sur les menaces, MITRE ATT&CK, a été conçu pour les menaces informatiques classiques et ne couvre pas nativement des techniques comme l'injection de prompt ou le *jailbreak*. Le référentiel MITRE ATLAS, dédié aux systèmes d'intelligence artificielle, répond à ce besoin, mais il introduit une autre difficulté : certaines de ses techniques sont proches les unes des autres, et un modèle peut proposer un identifiant qui existe bien dans la taxonomie sans pour autant correspondre à l'attaque décrite.

### Décrire l'attaque avec une granularité suffisante

Une défense n'est utile que si elle agit sur une partie précise de l'attaque. Savoir qu'un passage décrit « une injection de prompt » ne suffit pas pour choisir une contre-mesure : il faut savoir par quel canal l'instruction malveillante entre dans le système, quel mécanisme lui permet de contourner les protections et quel effet elle produit. Sans cette granularité, la recommandation reste générique et risque de ne pas correspondre à l'attaque étudiée.

### Maîtriser les hallucinations et vérifier les recommandations

Même lorsque des cas pertinents sont retrouvés, le modèle chargé de rédiger la recommandation peut s'en écarter, ajouter des éléments non justifiés ou reprendre une défense qui ne s'applique pas à l'attaque. Il faut donc vérifier chaque recommandation avant de la proposer. Une solution courante consiste à demander au modèle de relire et de corriger sa propre réponse, mais plusieurs travaux montrent que cette auto-correction est peu fiable : un modèle a tendance à juger favorablement ce qu'il a lui-même produit (Xu et al., 2024 ; Kamoi et al., 2024). Se pose alors la question de savoir comment vérifier une recommandation sans dépendre du modèle qui l'a générée, et surtout de savoir ce que cette vérification garantit réellement.

Ces difficultés ne sont pas indépendantes. Une erreur commise lors de l'extraction ou du rattachement à la taxonomie peut fausser la recherche des cas similaires, et une recherche faussée peut conduire à une recommandation correctement citée mais inadaptée. Le problème ne se réduit donc pas à la qualité de chaque étape prise isolément : il porte aussi sur la manière dont les erreurs se transmettent d'une étape à l'autre.

## 1.3 Question de recherche

Ces constats conduisent à formuler la question centrale de ce mémoire :

**Comment exploiter les connaissances issues de la littérature scientifique en cybersécurité pour générer des recommandations de défense précises, contextualisées et vérifiables, tout en maîtrisant les hallucinations, le manque de granularité et les déviations des modèles de langage ?**

Cette question comporte deux versants. Le premier est un objectif : obtenir des recommandations précises, contextualisées et vérifiables. Le second désigne les obstacles à maîtriser : les hallucinations, qui conduisent le modèle à produire des contenus non fondés ; le manque de granularité, qui rend les recommandations trop générales ; et les déviations, par lesquelles le modèle s'écarte des sources qu'il est censé utiliser ou valide ses propres erreurs.

Pour y répondre, ce travail ne se limite pas à proposer une approche ; il cherche aussi à évaluer ce que chaque mécanisme de contrôle garantit réellement. Il ne suffit pas, par exemple, qu'un identifiant soit accepté par la taxonomie, qu'un cas soit jugé proche de l'attaque ou qu'une recommandation cite une source : il faut mesurer si l'identifiant est correct, si le cas est pertinent et si la recommandation constitue une défense adaptée.

## 1.4 Conclusion

Ce chapitre a précisé le problème étudié : transformer une littérature scientifique abondante et dispersée en recommandations de défense fiables contre les attaques visant les LLM. Il a mis en évidence quatre difficultés, liées à l'extraction des connaissances, à leur ancrage dans une taxonomie, à la granularité de la description des attaques et à la vérification des recommandations, ainsi que le risque de voir les erreurs se propager d'une étape à l'autre. Le chapitre suivant présente les travaux existants qui exploitent des textes de cybersécurité à l'aide de modèles de langage, afin d'identifier dans quelle mesure ils répondent à ces difficultés.

---

# Chapitre 2 — État de l'art

Le chapitre précédent a mis en évidence quatre difficultés : extraire des connaissances fiables d'articles hétérogènes, les ancrer dans une taxonomie adaptée, décrire les attaques avec une granularité suffisante et vérifier les recommandations produites. Ce chapitre présente les travaux qui se rapprochent le plus de notre problème. Nous avons retenu six approches, publiées entre 2023 et 2025, qui exploitent des textes de cybersécurité à l'aide de modèles de langage ou qui traitent d'un mécanisme que notre travail réutilise.

Ces six approches se répartissent en deux groupes. Les trois premières, CTINexus, LADDER et FALCON, partent de rapports de renseignement sur les menaces (CTI) et les transforment en connaissances structurées, voire en défenses : elles représentent la chaîne qui va du texte brut à la protection. Les trois suivantes, TechniqueRAG, ATAG et Self-Refine, ne couvrent pas toute cette chaîne, mais chacune traite une étape précise que notre approche doit également réaliser : classer une attaque dans une taxonomie, constituer une base de connaissances sur les vulnérabilités des LLM, et corriger les réponses d'un modèle. Chaque approche est analysée selon la même grille : son principe, sa méthodologie, ses contributions et résultats, ses limites, et sa relation avec notre travail. Les résultats chiffrés sont ceux rapportés par les auteurs.

## 2.1 CTINexus : construction de graphes de connaissances CTI par apprentissage en contexte

### Principe

CTINexus (Cheng et al., 2025) s'attaque à un problème bien connu du renseignement sur les menaces : les rapports CTI sont rédigés en langage naturel, ce qui rend difficile leur exploitation automatique, et les méthodes d'extraction classiques demandent de grandes quantités de données annotées. L'idée centrale est d'utiliser un LLM guidé par quelques exemples (apprentissage en contexte) pour extraire des connaissances d'un rapport et les organiser sous la forme d'un graphe de connaissances, sans réentraîner le modèle.

### Méthodologie et techniques utilisées

L'approche enchaîne trois étapes. La première extrait des triplets de la forme entité–relation–entité à partir du texte du rapport ; les exemples fournis au LLM sont choisis de manière optimisée pour guider l'extraction. La deuxième réalise un alignement hiérarchique des entités, afin de fusionner les mentions qui désignent le même objet, par exemple un même logiciel malveillant cité sous plusieurs formes. La troisième prédit des relations à longue distance : elle identifie des nœuds centraux et infère des liens entre des sous-graphes qui restaient déconnectés, pour obtenir un graphe plus complet. L'ontologie utilisée peut être modifiée en fournissant de nouveaux exemples annotés.

### Contributions et résultats

La contribution principale est un cadre de construction automatique de graphes de connaissances CTI qui fonctionne avec très peu d'annotations et s'adapte à différentes ontologies. Les auteurs l'évaluent sur des rapports CTI collectés auprès de dix plateformes et rapportent qu'il dépasse les méthodes existantes pour l'extraction de triplets, l'alignement des entités et la prédiction de relations.

### Limites

CTINexus produit une représentation structurée des menaces, mais ne va pas jusqu'à la défense : le graphe décrit les acteurs, les outils et les relations, sans proposer de contre-mesure à une attaque donnée. Il porte sur des rapports CTI consacrés aux menaces informatiques classiques, et non sur les attaques visant les LLM. Enfin, les entités et relations extraites ne sont pas rattachées à une taxonomie de référence des techniques d'attaque, ce qui limite la comparaison entre rapports au niveau des techniques.

### Relation avec notre travail

CTINexus montre qu'un LLM peut extraire des connaissances structurées d'un texte de sécurité sans réentraînement, ce que nous reprenons pour l'extraction des attaques et des défenses à partir d'articles. Il illustre aussi l'intérêt de passer par des entités avant d'aller vers une représentation plus riche. En revanche, son absence de défense produite et de rattachement à une taxonomie motive deux choix de notre approche : produire une recommandation de défense et ancrer chaque cas dans MITRE ATLAS.

## 2.2 LADDER : extraction de schémas d'attaque reliés à MITRE ATT&CK

### Principe

LADDER (Alam et al., 2023) part d'un constat : le renseignement sur les menaces s'appuie souvent sur des indicateurs de compromission (IoC), comme des adresses IP ou des noms de domaine, qui perdent rapidement leur valeur car un attaquant peut les changer facilement. Les auteurs proposent de s'intéresser plutôt aux schémas d'attaque, c'est-à-dire à la manière dont l'attaque se déroule, qui sont plus stables dans le temps. LADDER extrait ces schémas à partir de rapports CTI et les relie aux techniques de MITRE ATT&CK.

### Méthodologie et techniques utilisées

LADDER est un cadre d'extraction de connaissances fondé sur des modèles de type *transformer* de la famille BERT, appliqués à la reconnaissance d'entités et à l'identification des phrases qui décrivent un comportement d'attaque. Les schémas extraits sont ensuite classés vers les techniques de MITRE ATT&CK, puis organisés dans un graphe de connaissances qui décrit les différentes phases de l'attaque. Les auteurs appliquent le cadre à des rapports portant sur les environnements Android et les réseaux d'entreprise.

### Contributions et résultats

LADDER apporte une méthode d'extraction à grande échelle des schémas d'attaque, au-delà des simples indicateurs, ainsi qu'un rattachement systématique à une taxonomie reconnue. Les auteurs publient également un jeu de données de référence, en accès libre, destiné à l'entraînement et à l'évaluation de futurs modèles CTI.

### Limites

Comme CTINexus, LADDER décrit les attaques sans proposer de défense. Son rattachement taxonomique se fait vers MITRE ATT&CK, qui couvre les menaces informatiques classiques mais pas nativement les techniques propres aux LLM, comme l'injection de prompt ou le *jailbreak*. Enfin, l'approche repose sur des modèles entraînés sur des données annotées, ce qui suppose de disposer de telles données pour un nouveau domaine.

### Relation avec notre travail

LADDER confirme qu'il est préférable de raisonner sur le mécanisme d'une attaque plutôt que sur des indicateurs isolés ; c'est l'idée que nous poussons plus loin en décrivant chaque attaque par une chaîne causale. Son rattachement des schémas d'attaque à une taxonomie est également un principe que nous reprenons. La différence tient au choix de la taxonomie : les attaques que nous étudions visent des LLM, ce qui nous conduit à utiliser MITRE ATLAS plutôt qu'ATT&CK.

## 2.3 FALCON : génération de règles de détection à partir de la CTI

### Principe

FALCON (Mitra et al., 2025) va plus loin que les deux approches précédentes, puisqu'il ne se limite pas à extraire des connaissances : il produit directement des défenses. Son objectif est de transformer le renseignement sur les menaces en règles de détection déployables dans des systèmes de détection d'intrusion (IDS), afin de réduire le travail manuel des analystes chargés d'écrire ces règles.

### Méthodologie et techniques utilisées

FALCON est un cadre agentique fondé sur un LLM. À partir d'un contenu CTI, il retrouve des règles existantes, génère de nouvelles règles au format Snort, pour la détection réseau, et YARA, pour la détection de fichiers malveillants, puis les fait passer par plusieurs phases de validation. Ces phases combinent des vérifications automatiques et une boucle d'auto-réflexion, dans laquelle le modèle examine et améliore les règles qu'il a produites.

### Contributions et résultats

FALCON est l'une des premières approches à produire, à partir de la CTI, des artefacts de défense directement utilisables plutôt que du texte libre. Les auteurs rapportent une exactitude moyenne de 95 % pour la génération de règles, ainsi qu'un accord inter-évaluateurs de 84 % entre plusieurs analystes en cybersécurité lors d'une évaluation qualitative.

### Limites

La qualité des règles est contrôlée en partie par le modèle qui les a générées. Or, plusieurs travaux montrent qu'un LLM a tendance à juger favorablement ses propres productions (Xu et al., 2024 ; Kamoi et al., 2024), ce qui fragilise ce type de validation. Par ailleurs, FALCON porte sur des attaques réseau et système, et non sur les attaques visant les LLM. Enfin, les règles produites ne sont pas présentées comme rattachées à un cas documenté ou à un article source qui permettrait à un analyste de retracer d'où vient chaque défense.

### Relation avec notre travail

FALCON montre qu'il est possible de passer de la CTI à une défense concrète, ce qui correspond à l'objectif de notre travail. Il en révèle aussi le point faible : lorsque la vérification dépend du modèle générateur, elle hérite de ses biais. Cette limite motive l'un de nos choix principaux, qui consiste à séparer la vérification de la génération et à la confier à une règle déterministe, extérieure au LLM.

## 2.4 TechniqueRAG : classification des techniques d'attaque par génération augmentée

### Principe

TechniqueRAG (Lekssays et al., 2025) traite une étape précise de l'analyse des menaces : associer un passage de texte CTI à la technique d'attaque correspondante dans MITRE ATT&CK. Cette tâche est difficile en raison du nombre élevé de techniques et de la proximité de certaines d'entre elles. L'idée centrale est de ne pas demander au modèle de choisir librement parmi toutes les techniques, mais de lui fournir des candidats retrouvés dans une base de connaissances.

### Méthodologie et techniques utilisées

L'approche repose sur une génération augmentée par la recherche (RAG) spécialisée pour le domaine. Un module de recherche retrouve, pour un passage donné, des techniques et des exemples pertinents ; un LLM réordonne ensuite ces candidats (*re-ranking*) avant de produire l'annotation finale. Cette combinaison permet de restreindre l'espace de décision du modèle tout en exploitant sa capacité de compréhension du texte.

### Contributions et résultats

TechniqueRAG obtient de meilleurs résultats qu'une classification directe sans recherche. Les auteurs rapportent notamment un F1 de 91,1 % sur le jeu de données *Procedures* et de 50,2 % sur le jeu *Expert*, plus complexe. L'écart entre ces deux résultats montre que la tâche reste difficile lorsque les descriptions sont moins standardisées.

### Limites

TechniqueRAG évalue si l'étiquette produite pour un passage est correcte ; il ne mesure pas ce que devient une erreur de classification lorsqu'elle est utilisée par les étapes suivantes d'un système, par exemple pour retrouver des cas similaires ou proposer une défense. L'approche cible par ailleurs MITRE ATT&CK, et non les techniques propres aux attaques contre les LLM.

### Relation avec notre travail

TechniqueRAG valide une idée que nous reprenons : restreindre les techniques proposées au modèle à une liste de candidats et vérifier l'identifiant produit, plutôt que de laisser le modèle choisir librement. Notre approche applique ce principe à MITRE ATLAS. La lacune qu'il laisse ouverte, l'effet d'une erreur de classification sur la suite du traitement, est précisément l'une des questions que nous étudions dans l'évaluation.

## 2.5 ATAG : graphes d'attaque et base de vulnérabilités des LLM

### Principe

ATAG (Gandhi et al., 2025) s'intéresse à l'évaluation des risques dans les applications fondées sur plusieurs agents LLM. Ces systèmes sont difficiles à analyser, car leurs composants interagissent et les vulnérabilités des LLM évoluent rapidement. Les auteurs proposent de représenter ces risques sous la forme de graphes d'attaque, qui montrent comment un attaquant peut enchaîner plusieurs étapes, par exemple une injection de prompt qui se propage d'un agent à l'autre.

### Méthodologie et techniques utilisées

ATAG étend l'outil MulVAL, qui génère des graphes d'attaque par raisonnement logique, en lui ajoutant des faits et des règles d'interaction propres aux applications à agents IA. Le raisonnement est déductif : il repose sur des règles logiques plutôt que sur la réutilisation de cas. Pour alimenter ce raisonnement, les auteurs constituent une base de connaissances, la *LLM Vulnerability Database* (LVD), qui associe des vulnérabilités des LLM, des techniques MITRE et des procédures d'attaque décrites dans des articles de recherche, chaque enregistrement étant rattaché à MITRE ATLAS.

### Contributions et résultats

ATAG propose un cadre de modélisation des menaces adapté aux applications à agents LLM, appliqué à deux applications multi-agents. La LVD constitue une contribution importante pour notre sujet, car elle repose sur la même idée que la nôtre : la littérature sur les attaques contre les LLM peut être transformée en une base de connaissances structurée et ancrée dans une taxonomie. Elle compte 44 enregistrements, issus de trois articles et d'implémentations d'attaques réalisées par les auteurs.

### Limites

La LVD est constituée manuellement : ses enregistrements sont extraits et croisés à la main, et les auteurs citent eux-mêmes la dérivation automatique de stratégies de mitigation comme une perspective de travail. Le coût de cette construction manuelle n'est pas mesuré, et la base reste de petite taille. Par ailleurs, ATAG sert à évaluer les risques d'une application déjà déployée, et non à recommander une défense face à une attaque nouvellement signalée.

### Relation avec notre travail

ATAG est le travail le plus proche du nôtre par la nature de ses données. Il confirme l'intérêt d'une base de cas ancrée dans MITRE ATLAS et issue de la littérature. Notre approche se distingue en construisant cette base automatiquement, puis en mesurant ce que cette automatisation coûte par rapport à une base relue à la main, une question que la construction manuelle de la LVD ne permet pas de poser.

## 2.6 Self-Refine : amélioration itérative par auto-évaluation

### Principe

Self-Refine (Madaan et al., 2023) propose d'améliorer la réponse d'un LLM sans entraînement supplémentaire, en s'inspirant de la manière dont un humain relit et corrige son propre travail. Le modèle produit une première réponse, la critique, puis la révise en tenant compte de sa critique.

### Méthodologie et techniques utilisées

Un seul et même LLM joue trois rôles : il génère la réponse initiale, fournit un retour sur cette réponse, puis produit une version améliorée. Ce cycle peut être répété plusieurs fois. L'approche ne nécessite ni données supervisées, ni entraînement supplémentaire, ni apprentissage par renforcement. Une approche voisine, Reflexion (Shinn et al., 2023), utilise également un retour verbal produit par le modèle pour améliorer ses tentatives successives.

### Contributions et résultats

Les auteurs évaluent Self-Refine sur sept tâches variées, de la génération de réponses de dialogue au raisonnement mathématique, avec des modèles de la famille GPT, dont GPT-4. Ils rapportent une amélioration moyenne d'environ 20 points (en absolu) par rapport à une génération en une seule étape, selon des évaluations humaines et automatiques.

### Limites

L'efficacité de Self-Refine dépend de la capacité du modèle à juger correctement sa propre réponse. Or, des travaux ultérieurs montrent que les LLM ont tendance à surévaluer leurs propres productions, un biais qui s'amplifie au fil des itérations d'auto-raffinement (Xu et al., 2024). Une revue critique conclut par ailleurs que les gains d'auto-correction annoncés résistent rarement à une évaluation équitable face à des références contrôlées (Kamoi et al., 2024). Self-Refine n'a pas non plus été conçu pour vérifier qu'une réponse s'appuie sur une source.

### Relation avec notre travail

Self-Refine apporte l'idée d'un cycle « proposer, vérifier, réviser », que nous reprenons pour la production des recommandations. Ses limites justifient toutefois une différence essentielle : dans notre approche, l'étape de vérification n'est pas confiée au modèle qui a produit la recommandation, mais à une règle déterministe. Self-Refine sert également de point de comparaison dans notre évaluation, afin de mesurer ce que l'auto-vérification par le même modèle garantit réellement.

## 2.7 Autres travaux connexes

D'autres travaux complètent ce panorama sans être analysés en détail ici. Le raisonnement à partir de cas, formalisé par le cycle « retrouver, réutiliser, réviser, retenir » (Aamodt et Plaza, 1994), a récemment été combiné à la génération augmentée par la recherche : CBR-RAG (Wiratunga et al., 2024) structure la recherche autour de cas similaires et montre que cette organisation améliore la qualité des réponses dans le domaine juridique. Dans le domaine de la réponse aux incidents, CyberRAG (Blefari et al., 2026) classe une attaque à partir d'alertes de détection d'intrusion, retrouve un contexte pertinent et génère un rapport accompagné de recommandations, mais s'appuie sur le trafic réseau et sur une base interne à l'organisation plutôt que sur la littérature scientifique. Enfin, des outils comme RAGAS (Es et al., 2024) ou MiniCheck (Tang et al., 2024) mesurent si une réponse est fidèle au contexte retrouvé, une propriété proche de celle que contrôle notre vérificateur et dont nous discuterons les limites dans l'évaluation.

## 2.8 Conclusion

Les six approches étudiées couvrent, chacune, une partie du chemin qui mène d'un texte de sécurité à une défense. CTINexus et LADDER extraient et structurent les connaissances, FALCON produit des défenses, TechniqueRAG classe les attaques dans une taxonomie, ATAG constitue une base de vulnérabilités des LLM et Self-Refine corrige les réponses d'un modèle. Aucune, cependant, ne réunit l'ensemble de ces étapes pour les attaques visant les LLM, et aucune ne mesure comment l'erreur d'une étape se transmet aux suivantes. Le chapitre suivant compare ces approches de manière systématique afin de dégager précisément les besoins auxquels notre travail répond.

---

# Références bibliographiques

Aamodt, A. et Plaza, E. (1994). Case-Based Reasoning: Foundational Issues, Methodological Variations, and System Approaches. *AI Communications*, vol. 7, n° 1, p. 39–59.

Alam, M. T., Bhusal, D., Park, Y. et Rastogi, N. (2023). Looking Beyond IoCs: Automatically Extracting Attack Patterns from External CTI. *Proceedings of the 26th International Symposium on Research in Attacks, Intrusions and Defenses (RAID)*, p. 92–108.

Blefari, F., Cosentino, C., Pironti, F. A., Furfaro, A. et Marozzo, F. (2026). CyberRAG: An Agentic RAG Cyber Attack Classification and Reporting Tool. *Future Generation Computer Systems*, vol. 176, p. 108186.

Carlini, N., Jagielski, M., Choquette-Choo, C. A., Paleka, D., Pearce, W., Anderson, H., Terzis, A., Thomas, K. et Tramèr, F. (2024). Poisoning Web-Scale Training Datasets is Practical. *IEEE Symposium on Security and Privacy (SP)*, p. 407–425.

Cheng, Y., Bajaber, O., Tsegai, S. A., Song, D. et Gao, P. (2025). CTINexus: Automatic Cyber Threat Intelligence Knowledge Graph Construction Using Large Language Models. *IEEE European Symposium on Security and Privacy (EuroS&P)*.

Es, S., James, J., Espinosa Anke, L. et Schockaert, S. (2024). RAGAS: Automated Evaluation of Retrieval Augmented Generation. *Proceedings of the 18th Conference of the European Chapter of the Association for Computational Linguistics: System Demonstrations*, p. 150–158.

Gandhi, P. A., Shukla, A., Tayouri, D., Ifland, B., Elovici, Y., Puzis, R. et Shabtai, A. (2025). ATAG: AI-Agent Application Threat Assessment with Attack Graphs. *arXiv preprint arXiv:2506.02859*.

Greshake, K., Abdelnabi, S., Mishra, S., Endres, C., Holz, T. et Fritz, M. (2023). Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection. *Proceedings of the 16th ACM Workshop on Artificial Intelligence and Security (AISec)*, p. 79–90.

Kamoi, R., Zhang, Y., Zhang, N., Han, J. et Zhang, R. (2024). When Can LLMs Actually Correct Their Own Mistakes? A Critical Survey of Self-Correction of LLMs. *Transactions of the Association for Computational Linguistics*, vol. 12, p. 1417–1440.

Lekssays, A., Shukla, U., Sencar, H. T. et Parvez, M. R. (2025). TechniqueRAG: Retrieval Augmented Generation for Adversarial Technique Annotation in Cyber Threat Intelligence Text. *Findings of the Association for Computational Linguistics: ACL 2025*, p. 20913–20926.

Madaan, A., Tandon, N., Gupta, P., Hallinan, S., Gao, L., Wiegreffe, S., Alon, U., Dziri, N., Prabhumoye, S., Yang, Y., Gupta, S., Majumder, B. P., Hermann, K., Welleck, S., Yazdanbakhsh, A. et Clark, P. (2023). Self-Refine: Iterative Refinement with Self-Feedback. *Advances in Neural Information Processing Systems (NeurIPS)*, vol. 36, p. 46534–46594.

MITRE Corporation. MITRE ATLAS : Adversarial Threat Landscape for Artificial-Intelligence Systems. https://atlas.mitre.org — techniques AML.T0020 « Poison Training Data », AML.T0051 « LLM Prompt Injection », AML.T0054 « LLM Jailbreak ».

MITRE Corporation. MITRE ATT&CK. https://attack.mitre.org

Mitra, S., Neupane, S., Duclos, M., Mittal, S., Piplai, A., Rahman, M. R., Zieglar, E. et Rahimi, S. (2025). FALCON: Transforming Cyber Threat Intelligence into Deployable IDS Rules with Self-Reflection. *arXiv preprint arXiv:2508.18684*.

Niu, C., Wu, Y., Zhu, J., Xu, S., Shum, K., Zhong, R., Song, J. et Zhang, T. (2024). RAGTruth: A Hallucination Corpus for Developing Trustworthy Retrieval-Augmented Language Models. *Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (ACL)*, vol. 1, p. 10862–10878.

Shinn, N., Cassano, F., Berman, E., Gopinath, A., Narasimhan, K. et Yao, S. (2023). Reflexion: Language Agents with Verbal Reinforcement Learning. *Advances in Neural Information Processing Systems (NeurIPS)*, vol. 36, p. 8634–8652.

Tang, L., Laban, P. et Durrett, G. (2024). MiniCheck: Efficient Fact-Checking of LLMs on Grounding Documents. *Proceedings of the 2024 Conference on Empirical Methods in Natural Language Processing (EMNLP)*, p. 8818–8847.

Wei, A., Haghtalab, N. et Steinhardt, J. (2023). Jailbroken: How Does LLM Safety Training Fail? *Advances in Neural Information Processing Systems (NeurIPS)*, vol. 36.

Wiratunga, N., Abeyratne, R., Jayawardena, L., Martin, K., Massie, S., Nkisi-Orji, I., Weerasinghe, R., Liret, A. et Fleisch, B. (2024). CBR-RAG: Case-Based Reasoning for Retrieval Augmented Generation in LLMs for Legal Question Answering. *Proceedings of the 32nd International Conference on Case-Based Reasoning (ICCBR)*, LNCS vol. 14775, p. 445–460.

Xu, W., Zhu, G., Zhao, X., Pan, L., Li, L. et Wang, W. (2024). Pride and Prejudice: LLM Amplifies Self-Bias in Self-Refinement. *Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (ACL)*, vol. 1, p. 15474–15492.
