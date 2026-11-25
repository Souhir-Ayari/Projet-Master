# Chapitre 5 — Évaluations

Ce chapitre évalue CARL étape par étape. Il présente d'abord les données utilisées : le corpus d'articles, la base de cas construite à partir de ce corpus et les jeux de données de test. Il décrit ensuite le protocole expérimental, puis les résultats de chaque étape.

## 5.1 Données

### 5.1.1 Corpus scientifique

**Présentation des articles.** La base de cas de CARL est construite à partir d'un corpus de quatorze articles scientifiques consacrés aux attaques contre les LLM et à leurs défenses. Le corpus a été constitué en deux temps.

Trois articles ont servi au développement initial du pipeline :

- une étude de l'injection de prompt indirecte contre les applications intégrant un LLM (Greshake et al., 2023) ;
- une analyse théorique des limites de l'alignement des LLM (Wolf et al., 2023) ;
- une formalisation et un banc d'essai des attaques par injection de prompt et de leurs défenses (Liu et al., 2024).

Le corpus a ensuite été élargi avec onze articles publiés sur arXiv, présentés dans le tableau 5.1 et regroupés par famille d'attaques.

*Tableau 5.1 — Articles arXiv ajoutés au corpus, par famille d'attaques*

| Famille | Article | Nature de la contribution |
|---|---|---|
| Injection de prompt directe | *Ignore Previous Prompt: Attack Techniques For Language Models* (Perez et Ribeiro, 2022) | Attaque |
| Injection de prompt indirecte | *Benchmarking and Defending Against Indirect Prompt Injection Attacks on Large Language Models* (Yi et al., 2023) | Banc d'essai et défense |
| Injection de prompt | *StruQ: Defending Against Prompt Injection with Structured Queries* (Chen et al., 2024) | Défense |
| Agents avec outils | *InjecAgent: Benchmarking Indirect Prompt Injections in Tool-Integrated Large Language Model Agents* (Zhan et al., 2024) | Banc d'essai |
| *Jailbreak* | *Jailbroken: How Does LLM Safety Training Fail?* (Wei et al., 2023) | Analyse des attaques |
| *Jailbreak* | *Universal and Transferable Adversarial Attacks on Aligned Language Models* (Zou et al., 2023) | Attaque |
| *Jailbreak* | *Do Anything Now: Characterizing and Evaluating In-The-Wild Jailbreak Prompts on Large Language Models* (Shen et al., 2023) | Étude empirique |
| *Jailbreak* | *Jailbreaking Black Box Large Language Models in Twenty Queries* (Chao et al., 2023) | Attaque |
| *Jailbreak* | *SmoothLLM: Defending Large Language Models Against Jailbreaking Attacks* (Robey et al., 2023) | Défense |
| *Jailbreak* | *Baseline Defenses for Adversarial Attacks Against Aligned Language Models* (Jain et al., 2023) | Défense |
| Empoisonnement des données | *Poisoning Language Models During Instruction Tuning* (Wan et al., 2023) | Attaque |

**Types de publications étudiées.** Le corpus ne contient pas de rapports CTI ni de bulletins de sécurité, mais uniquement des articles de recherche. Ils sont de quatre natures :

- des articles qui **proposent une attaque** et la démontrent sur des modèles ou des applications ;
- des articles qui **proposent une défense** et mesurent son efficacité ;
- des **bancs d'essai** (*benchmarks*), qui évaluent de manière systématique plusieurs attaques et défenses ;
- des **analyses** des attaques, empiriques ou théoriques, qui expliquent pourquoi les protections échouent.

Cette variété est volontaire. Un article d'attaque fournit surtout la description d'une attaque, souvent sans défense : il produit des cas avec une défense « null ». Un article de défense ou un banc d'essai fournit au contraire des mesures de protection. Le corpus permet ainsi de vérifier que le pipeline sait distinguer ces deux situations.

**Pourquoi ces articles ont été sélectionnés.** Les articles ajoutés ont été choisis selon trois critères.

1. *Couvrir plusieurs fois les mêmes techniques.* Les articles portent sur les techniques déjà présentes dans les trois premiers articles : injection de prompt directe, indirecte et déclenchée, *jailbreak* et empoisonnement. Avoir plusieurs cas d'une même technique, issus d'articles différents, donne à la recherche de cas de vrais choix à faire.
2. *Inclure des articles de défense.* Un cas sans défense n'aide pas à recommander une mesure. Des articles centrés sur la défense (StruQ, BIPIA, SmoothLLM et les défenses de base de Jain et al.) ont donc été ajoutés.
3. *Exclure volontairement certaines attaques.* Aucun article ne porte sur l'inférence d'appartenance, l'extraction de modèle, l'extraction de données d'entraînement ou les exemples adverses sur des images. Ces attaques sont réservées aux requêtes de test hors corpus : elles servent à vérifier si CARL signale correctement qu'aucun cas de sa base ne couvre une attaque. Les inclure dans le corpus supprimerait ces exemples négatifs.

Avant chaque téléchargement, le titre de l'article sur arXiv est comparé au titre attendu, afin d'éviter d'intégrer un mauvais document. Il faut noter enfin que le corpus est dominé par l'injection de prompt et le *jailbreak*. Il suffit pour construire et tester le pipeline, mais pas pour prétendre couvrir l'ensemble des attaques contre les LLM.

### 5.1.2 Constitution de la base de cas

Les quatorze articles ont été traités par la phase hors ligne décrite au chapitre 4. Le tableau 5.2 suit le nombre de cas à chaque étape. Ces effectifs servent de dénominateurs à tous les taux présentés dans la suite du chapitre.

*Tableau 5.2 — Du corpus à la base de cas : effectifs à chaque étape (rapporté)*

| Étape | Effectif | Définition |
|---|---|---|
| Articles traités | 14 | Nombre d'articles scientifiques dont au moins un cas figure dans la base |
| Passages analysés par la couche 2 | 263 | Nombre de passages de texte (*chunks*) découpés dans les 14 articles et lus par Mistral-7B |
| Passages décrivant une attaque confirmée | 212 | Passages que la couche 2 a jugés comme décrivant une attaque concrète ; les autres (résultats, état de l'art, protocole…) sont écartés |
| Cas après déduplication (base construite) | 119 | Cas conservés après la limite de 3 cas par couple (article, technique), qui supprime les reformulations d'une même attaque ; c'est la base utilisée dans toutes les expériences |
| dont identifiant ATLAS validé / abstention | 107 / 12 | 107 cas ont un identifiant MITRE ATLAS qui a passé les deux contrôles ; 12 cas n'ont reçu aucun identifiant (abstention) |
| dont défense extraite / « null » explicite | 92 / 27 | 92 cas ont un résumé de défense ; 27 cas portent « null », car le passage ne propose aucune défense |
| Cas retirés à la revue (pas une attaque) | 11 | Cas que la revue manuelle a jugés ne pas décrire une attaque (énoncé général, résultat d'expérience…) |
| Cas retenus après revue (base révisée) | 108 | 119 − 11 : cas qui décrivent réellement une attaque ; base utilisée seulement comme borne supérieure |

*Lecture : chaque ligne compte des passages ou des cas ; les lignes « dont » détaillent les 119 cas de la base construite.*

**Base construite.** La couche 2 a analysé 263 passages, dont 212 décrivent une attaque confirmée. La déduplication, qui conserve au plus trois cas par couple (article, technique), ramène ce nombre à 119 cas. Parmi eux, 107 ont reçu un identifiant ATLAS qui a passé la validation, et 12 une abstention ; 92 comportent une défense extraite, et 27 une valeur « null » explicite. Toutes les expériences sont menées sur cette base, **telle que le pipeline l'a produite, sans correction manuelle**. C'est en effet la construction automatique qui distingue CARL des bases construites à la main, comme la LVD d'ATAG (Gandhi et al., 2025) : il faut donc évaluer ce que produit réellement l'automatisation.

**Base révisée.** Les 119 cas ont ensuite été relus un par un. Cette revue a conduit à une seconde version de la base, dite *révisée* : 11 enregistrements qui ne décrivent pas une attaque ont été retirés, les identifiants erronés ont été corrigés, et les défenses qui ne sont pas de véritables contre-mesures ont été remplacées par « null ». Elle compte 108 cas, dont 84 concernent le *jailbreak* ou l'injection de prompt. Cette base révisée n'est jamais utilisée comme base de travail : elle sert seulement de **borne supérieure**, pour estimer ce qu'obtiendrait CARL si sa classification était sans erreur.

### 5.1.3 Jeux de données de test

Chaque étape de CARL est évaluée sur un jeu de données adapté à ce qu'elle doit produire. Le tableau 5.3 les récapitule.

*Tableau 5.3 — Jeux de données de test et étape évaluée*

| Jeu de données | Taille | Étape évaluée |
|---|---|---|
| Annotation manuelle des entités d'un article | 45 entités | Extraction (couche 1) |
| Revue manuelle de la base de cas | 119 cas (30 réannotés) | Classification ATLAS et défenses |
| Requêtes d'attaque rédigées à la main | 18 requêtes | Recherche de cas et recommandations |
| Paires de cas pour la calibration | 20 paires | Seuils du vérificateur causal |
| Recommandations soumises à des évaluateurs | 76 recommandations | Évaluation humaine |

**Annotation des entités.** Un article du corpus (Greshake et al., 2023) a été annoté à la main avec les sept étiquettes de la couche 1 : il contient 45 entités. Cette annotation sert de référence pour évaluer l'extraction.

**Revue de la base de cas.** Le pipeline vérifie qu'un identifiant ATLAS est *valide*, mais pas qu'il est *correct*. Pour le savoir, chacun des 119 cas a été relu afin de répondre à quatre questions : le cas décrit-il une attaque ? la technique est-elle correcte ? la défense est-elle une vraie contre-mesure ? la valeur « null » est-elle justifiée ? Un assistant LLM a proposé une première réponse, que nous avons vérifiée cas par cas. Comme aucun second annotateur n'était disponible, 30 cas ont été annotés une seconde fois pour mesurer la cohérence de la revue.

**Requêtes d'attaque.** Une requête est une courte description d'attaque, comme celle qu'un analyste pourrait soumettre à CARL. Nous en avons rédigé 18, avant de regarder le contenu de la base :

- **14 requêtes couvertes** : elles portent sur des attaques présentes dans la base (injection de prompt, *jailbreak*, empoisonnement…). CARL doit retrouver un cas pertinent et proposer une défense ;
- **4 requêtes hors corpus** : elles portent sur des attaques volontairement exclues du corpus (inférence d'appartenance, extraction de modèle, extraction de données d'entraînement, perturbation adverse d'image). CARL doit signaler qu'aucun cas ne les couvre.

**Paires de calibration.** 20 paires de cas de même technique servent à fixer les seuils du vérificateur causal, sans utiliser les requêtes de test.

**Évaluation humaine.** 76 recommandations ont été notées par deux évaluateurs externes, doctorants.

## 5.2 Protocole expérimental

### 5.2.1 Principe de l'évaluation

L'évaluation ne se limite pas à juger la recommandation finale. Chaque étape de CARL est évaluée séparément, sur les mêmes cas, pour deux raisons. D'une part, une erreur commise au début du pipeline peut rester invisible à la fin : une recommandation peut être bien formée et citer un cas, alors que ce cas a été mal classé deux étapes plus tôt. D'autre part, chaque mécanisme de contrôle de CARL vérifie une propriété facile à mesurer, qui n'est pas exactement la propriété recherchée. L'évaluation compare donc, à chaque étape, ce que le mécanisme vérifie et ce qu'il est censé garantir.

Trois questions de recherche structurent cette comparaison, une par mécanisme de contrôle :

- **RQ1 — Classification.** Un identifiant MITRE ATLAS *valide* est-il aussi *correct* ? La validation garantit que l'identifiant existe et concerne les LLM ; la question est de savoir s'il désigne la bonne technique.
- **RQ2 — Recherche de cas.** Le cas le plus *proche* est-il vraiment un cas *pertinent* ? Le seuil de similarité est censé indiquer que la base couvre l'attaque ; la question est de savoir s'il le fait réellement.
- **RQ3 — Vérification des recommandations.** Une défense qui *cite* un cas est-elle une *bonne* défense ? La vérification garantit qu'une mesure est rattachée à un cas ; la question est de savoir si elle protège contre l'attaque.

L'extraction des entités, qui précède ces trois étapes, est évaluée en premier, car elle fournit le contexte de tout le reste du pipeline. Une évaluation humaine complète enfin les mesures automatiques.

### 5.2.2 Mesures utilisées à chaque étape

Le tableau 5.4 récapitule, pour chaque étape, le jeu de données, ce qui est comparé et les mesures utilisées.

*Tableau 5.4 — Protocole d'évaluation par étape*

| Étape | Jeu de données | Ce qui est comparé | Mesures |
|---|---|---|---|
| Extraction des entités | 45 entités annotées | GLiNER et Mistral-7B guidé par prompt ; effet de chaque filtre | Précision, rappel, F1, taux d'hallucination |
| RQ1 — Classification | Revue des 119 cas | Identifiant valide et identifiant correct | Taux de validité, taux d'exactitude, fiabilité des « null » et des abstentions, accord intra-annotateur |
| RQ2 — Recherche | 18 requêtes | Base construite et base révisée ; requêtes couvertes et hors corpus | Hit@1, Hit@3, MRR, similarité du meilleur cas |
| RQ3 — Recommandations | 18 requêtes, 20 paires de calibration | Génération sans recherche, recherche sans vérification, boucle avec vérification, variantes du vérificateur | Ancrage, taux d'hallucination, adaptation, adéquation causale, part des requêtes servies |
| Évaluation humaine | 76 recommandations | Les configurations de RQ3 | Échelles de 1 à 5, accord entre évaluateurs |

Le tableau se lit de haut en bas, dans l'ordre du pipeline. Pour l'extraction, les entités produites sont comparées à l'annotation manuelle. Pour RQ1, on compare la part d'identifiants valides à la part d'identifiants corrects selon la revue. Pour RQ2, on vérifie si les cas retrouvés sont pertinents (Hit@1 : le premier cas est pertinent ; Hit@3 : au moins un des trois l'est ; MRR : un cas pertinent compte d'autant plus qu'il est bien classé), et si le seuil θ sépare les requêtes couvertes des requêtes hors corpus. Pour RQ3, on mesure surtout l'*ancrage*, c'est-à-dire la part des recommandations rattachées à un cas qui les justifie, et la part des requêtes qui reçoivent une recommandation. L'évaluation humaine vérifie enfin si des lecteurs externes perçoivent les différences entre configurations.

Comme les effectifs sont petits, les taux sont accompagnés d'intervalles de confiance à 95 %, et la cohérence des annotations est mesurée par un coefficient d'accord (kappa de Cohen pour la revue, alpha de Krippendorff pour l'évaluation humaine).

## 5.3 Extraction des entités

Cette étape compare les méthodes envisagées pour la couche 1 sur l'article annoté (45 entités) : GLiNER, qui sélectionne des segments du texte, et quatre variantes de Mistral-7B guidé par un prompt, de plus en plus spécifiques. La variante *naïve* donne une simple consigne ; la variante *travaillée* (*engineered*) structure davantage la demande ; la variante *personnalisée* (*custom*) part d'un besoin formulé par l'utilisateur ; la variante *thématique* (*topic*) fournit la taxonomie des sept étiquettes avec leur description.

### 5.3.1 Choix de l'extracteur

*Tableau 5.5 — Comparaison des extracteurs de la couche 1 sur l'annotation manuelle (45 entités) (rapporté)*

| Méthode | Précision | Rappel | F1 | Taux d'hallucination |
|---|---|---|---|---|
| GLiNER (*zero-shot*) | 0,296 | 0,289 | 0,292 | 0,000 |
| Mistral-7B (naïve) | 0,104 | 0,667 | 0,180 | 0,010 |
| Mistral-7B (travaillée) | 0,115 | 0,244 | 0,156 | 0,000 |
| Mistral-7B (personnalisée) | 0,212 | 0,156 | 0,180 | 0,030 |
| Mistral-7B (thématique) | 0,121 | 0,467 | 0,192 | 0,017 |

*Le taux d'hallucination est la part des entités extraites absentes du texte de l'article.*

GLiNER obtient la meilleure précision et le meilleur F1, et n'extrait aucune entité absente du texte. Les variantes de Mistral-7B atteignent parfois un rappel plus élevé, mais au prix d'une précision faible. GLiNER est retenu surtout pour son taux d'hallucination nul : ses entités servent de contexte à la couche 2, et une entité inventée à ce stade serait transmise à toutes les étapes suivantes.

### 5.3.2 Contribution des filtres

Les filtres ont été évalués sur la variante thématique de Mistral-7B, en les ajoutant un par un aux mêmes sorties enregistrées du modèle.

*Tableau 5.6 — Contribution de chaque filtre (Mistral-7B, variante thématique) (rapporté)*

| Configuration | Précision | Rappel | F1 | Taux d'hallucination |
|---|---|---|---|---|
| Sans filtre | 0,083 | 0,511 | 0,143 | 0,011 |
| + liste blanche d'étiquettes | 0,089 | 0,467 | 0,150 | 0,013 |
| + longueur maximale | 0,116 | 0,467 | 0,186 | 0,017 |
| + fuite de l'exemple | 0,116 | 0,467 | 0,186 | 0,017 |
| + valeurs de remplissage | 0,116 | 0,467 | 0,186 | 0,017 |
| Système complet (+ format, bruit des citations) | 0,121 | 0,467 | 0,192 | 0,017 |

Le filtre de longueur maximale apporte le plus : il retire 54 prédictions, surtout des propositions descriptives plutôt que des entités, et fait passer la précision de 0,089 à 0,116 sans perdre aucune entité correcte. La liste blanche d'étiquettes est le seul filtre qui présente un compromis : elle écarte deux entités correctes que le modèle avait extraites sous une étiquette hors taxonomie, ce qui fait baisser le rappel de 0,511 à 0,467. Les filtres de fuite de l'exemple et des valeurs de remplissage n'ont aucun effet sur cet article ; ils corrigent des erreurs observées sur un corpus antérieur et servent ici de garde-fous. Au total, les filtres font passer le F1 de 0,143 à 0,192 (+34 %). La hausse apparente du taux d'hallucination, de 0,011 à 0,017, est un effet de dénominateur : les trois mêmes entités non présentes dans le texte restent, parmi un nombre plus faible de prédictions.

### 5.3.3 Limite de l'annotation

Les précisions sont faibles pour toutes les méthodes, mais elles sous-estiment la qualité réelle de l'extraction. Un contrôle de 30 faux positifs tirés au hasard dans la sortie de la variante thématique a montré que 17 d'entre eux (57 % ; intervalle de Wilson 39 %–73 %) étaient de vraies entités de l'article, que l'annotation avait omises : types d'applications, impacts cités dans la taxonomie propre à l'article, ou défense proposée. Les 13 autres étaient des fragments descriptifs, des étiquettes erronées ou du bruit d'extraction. La précision de 0,121 est donc une borne inférieure ; extrapolée aux 153 faux positifs, elle correspondrait à environ 0,62 (0,47–0,76), un ordre de grandeur donné à titre indicatif seulement.

Deux conséquences en découlent. D'une part, la précision absolue de toutes les méthodes du tableau 5.5 est sous-estimée. D'autre part, le classement des méthodes ne reste valable que si la part d'entités valides non annotées est comparable d'une méthode à l'autre, ce qui n'a pas été vérifié. C'est une raison supplémentaire de fonder le choix de GLiNER sur l'absence d'hallucination plutôt que sur le F1. Ces résultats portent enfin sur un seul article et une seule configuration.

## 5.4 Classification : validité et exactitude (RQ1)

**Question de recherche : une classification correcte dans MITRE ATLAS permet-elle réellement d'identifier correctement le cas d'attaque ?**

Cette section évalue la capacité de CARL à associer chaque attaque extraite à la technique ATLAS appropriée.

### 5.4.1 Objectif de l'expérience

CARL valide chaque identifiant ATLAS : il vérifie que l'identifiant existe et qu'il concerne les LLM. Mais un identifiant valide n'est pas forcément le bon. L'expérience mesure donc l'écart entre les identifiants *valides* et les identifiants *corrects*, en comparant la sortie de CARL à la revue manuelle des cas.

### 5.4.2 Résultats de la classification

*Tableau 5.7 — Résultats de la classification (rapporté ; intervalles de Wilson à 95 %)*

| Mesure | Résultat | Intervalle |
|---|---|---|
| Validité des identifiants ATLAS | 107 / 119 = 89,9 % | n.r. |
| Exactitude des identifiants validés | 47 / 99 = 47,5 % | 37,9 %–57,2 % |
| Fiabilité des valeurs « null » | 21 / 22 = 95,5 % | 78,2 %–99,2 % |
| Abstentions justifiées | 0 / 9 | n.r. |

- **Validité** : presque tous les identifiants passent la validation.
- **Exactitude** : moins de la moitié des identifiants validés désignent la bonne technique.
- **Valeurs « null »** : lorsque CARL indique qu'un article ne propose aucune défense, il a raison 21 fois sur 22.
- **Erreurs récurrentes** : 27 des 52 erreurs concernent le *jailbreak* (AML.T0054), et l'injection déclenchée (AML.T0051.002) n'est correcte qu'une fois sur 17.

### 5.4.3 Analyse des erreurs

Les erreurs ne sont pas dues au hasard. Le modèle confond surtout le *jailbreak*, qui vise les protections du modèle, et l'injection de prompt, qui détourne les instructions d'une application : dans les deux cas, l'attaque consiste à faire suivre au modèle des instructions malveillantes. La bonne technique figurait pourtant dans la liste des candidats, et fournir au modèle les définitions officielles d'ATLAS ne corrige pas la confusion (41,1 % et 39,8 % d'identifiants corrects, contre 47,5 %).

Ces erreurs ont des conséquences sur les étapes suivantes. La recherche de cas filtre les candidats par technique : un cas mal classé peut être écarté d'une requête à laquelle il répondait, ou proposé pour une attaque différente. La défense recommandée peut alors s'appuyer sur un cas qui ne correspond pas à l'attaque.

### 5.4.4 Discussion des résultats

La validation ATLAS apporte une garantie réelle mais limitée : elle empêche les identifiants inventés ou hors sujet, mais ne garantit la bonne technique qu'environ une fois sur deux. Un identifiant valide ne suffit donc pas à identifier correctement le cas d'attaque. Ces taux reposent sur une revue faite par une seule personne (kappa intra-annotateur de 0,62 pour la technique) et doivent être lus comme des bornes supérieures. RQ2 mesure ce que cette erreur coûte à la recherche des cas.

## 5.5 RQ2 — Évaluation de la récupération des cas similaires

**Question de recherche : le cas le plus proche retrouvé par CARL est-il vraiment un cas pertinent, et le seuil de similarité indique-t-il correctement quand la base ne couvre pas une attaque ?**

RQ1 a montré qu'un identifiant valide n'est correct qu'environ une fois sur deux. Cette section examine l'étape suivante : la recherche des cas sur lesquels s'appuiera la recommandation.

### 5.5.1 Objectif de l'expérience

CARL retrouve les trois cas les plus similaires (k = 3) si le meilleur dépasse le seuil θ = 0,6. L'expérience vérifie, sur les 18 requêtes, si le premier cas retrouvé est pertinent (Hit@1) et si le seuil signale les attaques non couvertes. La recherche est lancée sur la base automatique (119 cas) puis sur la base de référence (108 cas) : comme seules les techniques diffèrent, cette comparaison mesure l'effet des erreurs de classification.

### 5.5.2 Résultats de la récupération

*Tableau 5.8 — Récupération sur les 14 requêtes couvertes (rapporté)*

| Configuration | Base | Hit@1 | Hit@3 | MRR |
|---|---|---|---|---|
| Similarité seule (α = 0) | Automatique | 0,571 | 0,714 | 0,695 |
| Bonus de technique (α = 0,05) | Automatique | 0,571 | 0,857 | 0,707 |
| Filtre par technique (retenu) | Automatique | 0,571 | 0,786 | 0,716 |
| Filtre par technique (retenu) | Référence (108 cas) | 1,000 | 1,000 | 1,000 |

Sur la base automatique, le premier cas retrouvé est pertinent pour 8 requêtes sur 14 (Hit@1 = 0,571), et ce résultat ne change pas selon la configuration choisie. Le Hit@3 est plus élevé (0,786 avec le filtre retenu) : un cas pertinent se trouve souvent parmi les trois cas retournés, mais pas toujours en première position.

Les intervalles de confiance sont larges, car ils reposent sur 14 requêtes : pour toutes les configurations sur la base automatique, l'intervalle du Hit@1 va environ de 0,29 à 0,86. Les différences entre ces configurations ne sont donc pas significatives.

### 5.5.3 Impact des erreurs de classification sur la récupération

Avec la même configuration, la base de référence atteint un Hit@1 de 1,000, contre 0,571 pour la base automatique. Cette différence de 43 points est le seul écart du tableau que les intervalles de confiance permettent d'affirmer.

Ce résultat s'explique par le filtre par technique. Sur la base automatique, favoriser les cas qui portent la même technique que la requête fait remonter les cas mal classés autant que les cas pertinents. Une fois les techniques corrigées, le même filtre devient très efficace. Le point faible n'est donc pas le mécanisme de recherche lui-même, mais la classification de la couche 2 : l'erreur mesurée en RQ1 se retrouve directement dans la recherche.

Cette borne de 1,000 doit toutefois être lue avec prudence. Les techniques des requêtes et celles de la base de référence ont été attribuées par la même personne, ce qui rend cette borne optimiste.

### 5.5.4 Détection des attaques hors corpus

Pour tester le signal de couverture, nous avons comparé la similarité du meilleur cas retrouvé pour les requêtes couvertes et pour les requêtes hors corpus. Les deux groupes ne se séparent pas : trois des quatre requêtes hors corpus obtiennent une similarité de 0,689 à 0,747, supérieure au seuil de 0,6 et même supérieure à celle de plusieurs requêtes couvertes (0,617 à 0,683).

Aucun seuil ne corrige complètement ce problème. Le meilleur seuil sur ces requêtes (θ = 0,75) atteint une exactitude équilibrée de seulement 0,68, et le seuil retenu (θ = 0,6) atteint 0,63. Nous avons conservé θ = 0,6 pour ne pas ajuster le seuil sur les requêtes de test.

L'explication la plus probable est liée au corpus : comme tous les articles portent sur des attaques contre les LLM, toute requête qui décrit une attaque de ce type trouve un cas qui lui ressemble, même lorsque cette attaque n'est pas documentée dans la base.

### 5.5.5 Discussion des résultats

Ces résultats montrent qu'un cas proche n'est pas forcément un cas pertinent. Sur la base automatique, le premier cas retrouvé n'est pertinent que dans un peu plus d'une requête sur deux, et cette limite vient surtout des erreurs de classification plutôt que de la recherche elle-même.

Ils montrent aussi qu'une similarité élevée ne prouve pas que la base couvre l'attaque. Le seuil θ permet d'écarter les requêtes clairement étrangères au domaine, mais pas les attaques plausibles absentes de la base. C'est pourtant dans ce cas qu'un signal de couverture serait le plus utile, puisqu'il devrait déclencher l'ajout de nouveaux articles à la base.

**Réponse à RQ2.** Le cas le plus proche n'est pertinent que pour 57,1 % des requêtes sur la base automatique, contre 100 % sur la base de référence : les erreurs de classification coûtent 43 points de Hit@1. Le seuil de similarité ne signale pas de manière fiable les attaques non couvertes. La similarité ne garantit donc ni la pertinence du cas, ni la couverture de la base.

## 5.6 RQ3 — Évaluation de la qualité et de la vérification des recommandations de défense

**Question de recherche : une recommandation qui cite un cas, et passe donc la vérification, est-elle vraiment une bonne défense ?**

Les deux premières étapes ont montré que les cas retrouvés peuvent être mal classés ou peu pertinents. Cette section évalue la dernière étape : la production et la vérification des recommandations qui s'appuient sur ces cas.

### 5.6.1 Objectif de l'expérience

L'expérience vérifie si une recommandation rattachée à un cas, et donc acceptée par le vérificateur, est réellement adaptée à l'attaque. Plusieurs configurations sont comparées selon l'**ancrage** (part des recommandations justifiées par un cas cité), l'**adéquation causale** (la mesure vise un maillon réel de l'attaque) et l'**adaptation** (la mesure tient compte de la nouvelle attaque). Les résultats portent sur 13 requêtes couvertes : la requête sur l'extraction du prompt système, marquée hors corpus dans le fichier de requêtes, est exclue.

### 5.6.2 Comparaison des différentes configurations

*Tableau 5.9 — Qualité des recommandations sur la base automatique (13 requêtes couvertes) (rapporté)*

| Configuration | Recommandations (requêtes servies) | Ancrage | Adaptation | Adéquation causale | Hors corpus | Utilité moyenne (1–5) |
|---|---|---|---|---|---|---|
| LLM seul, sans récupération | 39 (13) | 0,00 | 0,56 | — | 12 | 3,4 |
| Récupération sans vérification | 38 (13) | 0,42 | 0,69 | 0,74 | 6 | 2,7 |
| Vérification lexicale | 17 (9) | 1,00 | — | — | 2 | 2,9 |
| Règle causale (seuils a priori) | 10 (6) | 1,00 | 0,50 | 1,00 | 1 | 3,7 |
| Règle causale avec étiquettes (seuils a priori) | 5 (3) | 1,00 | 0,60 | 1,00 | 0 | 3,8 |
| LLM juge (même modèle) | 29 (12) | 1,00 | 0,69 | 0,76 | 4 | 3,5 |
| Self-Refine (même modèle) | 39 (13) | 0,13 | 0,67 | 0,62 | 6 | 3,5 |
| **Étiquettes, seuils calibrés (CARL)** | **9 (7)** | **1,00** | **0,89** | **1,00** | **0** | **3,6** |
| Base de référence (borne supérieure) | 11 (9) | 1,00 | 1,00 | 1,00 | 4 | 3,8 |

*Hors corpus : recommandations renvoyées pour les attaques non couvertes, qui devraient être nulles. Utilité moyenne : note des deux évaluateurs humains (5.6.4).*

Sans récupération, le LLM produit 39 recommandations, mais aucune n'est rattachée à un cas : il donne des conseils généraux, et en propose douze pour des attaques que la base ne documente pas. Avec la récupération mais sans vérification, l'ancrage monte à 0,42 : plus de la moitié des recommandations restent sans appui.

Toutes les configurations avec vérification atteignent un ancrage de 1,00, mais elles servent un nombre très différent de requêtes. La vérification lexicale en sert 9, les règles causales aux seuils fixés a priori seulement 3 à 6, et notre configuration aux seuils calibrés en sert 7. À l'inverse, les deux configurations où le modèle se juge lui-même servent presque toutes les requêtes. Le LLM juge accepte 29 recommandations, avec une adéquation causale plus faible (0,76) et plus de deux fois plus d'appels au modèle. La critique de Self-Refine a approuvé le plan initial du modèle pour chacune des 16 requêtes avec des cas retrouvés : aucune révision n'a eu lieu, et seulement 13 % de ses recommandations sont ancrées.

### 5.6.3 Évaluation de l'ancrage et de la cohérence causale

Un ancrage de 1,00 ne doit pas être lu comme une preuve de qualité. Il est obtenu par construction : les recommandations qui ne passent pas la vérification sont supprimées. Deux mécanismes le rendent trompeur.

Le premier concerne la vérification lexicale. Elle exige que 60 % des mots de la recommandation figurent dans la défense citée, ce qui favorise la reprise mot pour mot plutôt que l'adaptation à la nouvelle attaque. Le second est plus important : la vérification hérite de la qualité des cas cités. Par exemple, pour un *jailbreak* caché dans une requête encodée en Base64, la boucle lexicale accepte la recommandation « revue régulière du code et vérification des modifications de la documentation ». Cette mesure est copiée d'un cas qui décrit un ver se propageant entre applications intégrant un LLM, et que le pipeline avait classé à tort comme *jailbreak*. La recommandation est parfaitement traçable, mais elle ne répond pas à l'attaque.

Les règles causales réduisent ce problème. En exigeant que chaque mesure casse un maillon de la chaîne causale de la nouvelle attaque, elles éliminent ce type de copie : toutes les recommandations acceptées sont causalement adéquates, et la règle avec étiquettes ne renvoie rien sur les attaques non couvertes. Le prix est la couverture : avec les seuils fixés a priori, seules 5 recommandations, sur 3 requêtes, sont acceptées. Les seuils calibrés (0,627 pour la similarité à la défense citée et 0,534 pour le maillon) permettent de servir 7 requêtes, avec une adaptation de 0,89. Trois des neuf recommandations reposent cependant sur une citation inférée, et le seuil sémantique reste peu discriminant (exactitude équilibrée de 0,63). Enfin, la génération n'est pas totalement déterministe : une seconde exécution de la même configuration a renvoyé 14 recommandations sur 9 requêtes, dont deux pour une attaque non couverte.

### 5.6.4 Évaluation humaine des recommandations

Deux évaluateurs externes, doctorants, non impliqués dans le projet, ont noté 76 recommandations distinctes tirées des configurations du tableau 5.9. Chaque recommandation a été notée de 1 à 5 sur trois critères, l'utilité, la solidité et l'applicabilité, avec en plus un jugement « j'appliquerais cette mesure ». Les évaluateurs voyaient l'attaque, la recommandation et la défense citée, dans un ordre aléatoire et sans connaître la configuration. Une différence de protocole doit être signalée : l'un des deux évaluateurs a reçu en plus un glossaire des termes techniques.

L'accord entre les deux évaluateurs est inférieur au hasard : l'alpha de Krippendorff vaut −0,31 pour l'utilité, −0,02 pour la solidité et −0,17 pour l'applicabilité. Le désaccord n'est pas uniforme. Les deux évaluateurs donnent une note faible aux recommandations sans rapport avec l'attaque, comme une revue de code contre un *jailbreak*, et une note élevée aux mesures ciblées, comme décoder les entrées en Base64 avant de les filtrer. Ils divergent en revanche sur les conseils généraux, que l'un accepte (utilité moyenne de 4,2) et que l'autre juge trop vagues (2,5).

En moyenne, l'utilité va de 2,7 (récupération sans vérification) et 2,9 (vérification lexicale) à 3,6–3,8 pour les vérificateurs causaux et la base de référence. La part des recommandations qu'un évaluateur appliquerait varie de 40 % à 80 %. Aucune comparaison avec notre configuration n'est significative (test de Wilcoxon par requête, toutes les valeurs p ≥ 0,34, avec 3 à 6 requêtes par comparaison). On remarque aussi que Self-Refine, dont seulement 13 % des recommandations sont ancrées, obtient une utilité moyenne de 3,5, pas plus faible que les configurations entièrement ancrées.

Nous ne tirons donc aucun classement de cette évaluation. Avec un accord inférieur au hasard et des documents différents pour les deux évaluateurs, elle ne permet ni de confirmer ni d'infirmer les mesures automatiques. Elle montre seulement que les lecteurs repèrent les recommandations clairement hors sujet, mais pas les conseils généraux plausibles.

### 5.6.5 Discussion des résultats

Ces résultats montrent qu'une recommandation appuyée par un cas cité n'est pas forcément adaptée à l'attaque. Un vérificateur peut contrôler le lien entre une mesure et sa source, mais il ne peut pas savoir si cette source est elle-même correcte, ni si elle répond à une autre attaque. Or RQ1 a montré qu'environ la moitié des techniques et plus d'un tiers des défenses extraites sont incorrectes.

La vérification hors du modèle reste néanmoins utile. Le vérificateur causal élimine les copies qui ne visent pas la nouvelle attaque et ne renvoie aucune recommandation pour les attaques non couvertes, alors que les approches où le modèle se juge lui-même acceptent presque tout. Ce gain a un coût : seules 7 des 13 requêtes reçoivent une recommandation. Le choix d'un vérificateur est donc un compromis entre le nombre de requêtes servies et la solidité des recommandations. Enfin, sur la base de référence, la boucle renvoie quatre recommandations pour des attaques non couvertes, parce que le seuil θ ne signale pas l'absence de couverture : le vérificateur ne peut pas compenser une erreur de l'étape précédente.

**Réponse à RQ3.** Une recommandation qui cite un cas n'est pas forcément une bonne défense. La vérification garantit la traçabilité, mais pas la pertinence de la mesure. Le vérificateur causal calibré réduit cet écart (adéquation causale de 1,00, adaptation de 0,89, aucune recommandation hors corpus), au prix d'une couverture limitée (7 requêtes sur 13). L'évaluation humaine, trop peu concordante, ne permet pas de trancher.

## 5.7 Synthèse globale des résultats expérimentaux

### 5.7.1 Synthèse des réponses aux questions de recherche

Chaque question de recherche comparait ce qu'un mécanisme de CARL vérifie à ce qu'il est censé garantir. Le tableau 5.10 résume les réponses.

*Tableau 5.10 — Synthèse des réponses aux questions de recherche*

| Question | Ce que CARL vérifie | Ce que l'on veut réellement | Résultat principal |
|---|---|---|---|
| RQ1 — Classification | L'identifiant est valide | L'identifiant est correct | 89,9 % valides, mais 47,5 % corrects |
| RQ2 — Récupération | Le cas est proche (similarité ≥ θ) | Le cas est pertinent et la base couvre l'attaque | Hit@1 de 0,571 contre 1,000 sans erreur de classification ; attaques hors corpus au-dessus du seuil |
| RQ3 — Recommandation | La mesure cite un cas | La mesure est une bonne défense | Ancrage de 1,00 par construction ; recommandations traçables mais parfois inadaptées |

Dans les trois cas, la propriété vérifiée est plus faible que la propriété recherchée. Chaque mécanisme apporte une garantie réelle (pas d'identifiant inventé, pas de recommandation sans source), mais cette garantie ne suffit pas à assurer la qualité du résultat.

### 5.7.2 Analyse de la propagation des erreurs

Ces écarts ne restent pas indépendants : l'erreur d'une étape se transmet à la suivante. L'erreur de classification de RQ1 se retrouve d'abord dans la récupération. Les deux bases ne diffèrent que par la correction des techniques, et cette seule correction fait passer le Hit@1 de 0,571 à 1,000. La perte de 43 points n'est donc pas une faiblesse de la recherche, mais l'erreur de classification qui arrive à l'étape suivante.

Cette même erreur se retrouve ensuite dans les recommandations. Un vérificateur qui contrôle la traçabilité accepte une mesure dès qu'elle est rattachée à un cas, même si ce cas est mal classé ou si sa défense n'est pas une vraie contre-mesure. L'exemple du *jailbreak* en Base64 montre cette propagation de bout en bout : la technique est validée, le cas est retrouvé, la recommandation est traçable, et pourtant la mesure ne répond pas à l'attaque. Chaque contrôle est satisfait, mais l'erreur se trouve dans l'enchaînement des étapes.

Il en découle une conséquence pour l'évaluation : un ancrage de 1,00 à la dernière étape ne veut rien dire si l'on ne connaît pas la qualité des étapes précédentes, puisqu'un pipeline peut atteindre 1,00 à la fin tout en ayant hérité de 47,5 % d'exactitude au début. C'est pourquoi nous avons mesuré la validité et l'exactitude séparément à chaque étape, sur les mêmes cas. Ces mesures de propagation héritent toutefois des limites de la revue : une seule annotatrice et un petit nombre de requêtes.

### 5.7.3 Réponse à la problématique générale

La problématique de ce mémoire demandait comment exploiter la littérature scientifique pour produire des recommandations de défense précises, contextualisées et vérifiables, en maîtrisant les hallucinations, le manque de granularité et les déviations des modèles de langage.

Les résultats apportent une réponse en partie positive. CARL construit automatiquement une base de cas à partir d'articles, enregistre de façon fiable l'absence de défense (« null » justifié 21 fois sur 22), et produit des recommandations vérifiables : chacune cite son cas, et la vérification hors du modèle évite l'auto-validation observée avec Self-Refine. La chaîne causale apporte de la granularité, puisque les mesures acceptées visent un maillon précis de l'attaque.

Les résultats montrent aussi les limites de cette réponse. Une recommandation vérifiable n'est pas forcément précise : la qualité finale dépend de la classification, qui reste le point faible du pipeline avec un modèle de 7 milliards de paramètres. Le seuil de similarité ne permet pas de savoir de manière fiable quand la base ne couvre pas une attaque. Enfin, ces conclusions reposent sur un corpus de 14 articles, 18 requêtes et une revue réalisée par une seule personne.

L'apport principal de CARL n'est donc pas d'éliminer les erreurs, mais de les rendre mesurables. Parce que chaque recommandation est traçable, il est possible de remonter à l'étape qui a produit l'erreur et de mesurer comment elle se propage. Ces constats sont discutés plus en détail dans le chapitre suivant.
