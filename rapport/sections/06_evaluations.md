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

**Annotation des entités.** Pour évaluer l'extraction, nous avons annoté manuellement un article du corpus (Greshake et al., 2023) avec les sept étiquettes de la couche 1. L'annotation contient 45 entités distinctes. Chacune a été vérifiée comme présente dans le texte produit par notre extraction PDF, bibliographie exclue, afin qu'une entité absente du texte lu par le pipeline ne soit pas comptée comme une erreur du modèle.

**Revue de la base de cas.** Le pipeline contrôle qu'un identifiant ATLAS est *valide*, c'est-à-dire qu'il existe et qu'il appartient à la liste des techniques liées aux LLM. Il ne peut pas contrôler qu'il est *correct*, c'est-à-dire qu'il désigne bien la technique de l'attaque décrite. Pour mesurer cette exactitude, il faut disposer d'une réponse de référence pour chaque cas. Aucune référence n'existant pour cette base, nous l'avons construite en relisant chacun des 119 cas. Pour chaque cas, la revue répond à quatre questions :

1. **Le cas décrit-il réellement une attaque ?** Certains enregistrements ne contiennent qu'un énoncé général ou un résultat d'expérience.
2. **La technique ATLAS attribuée est-elle correcte ?** Par exemple, une attaque de type *jailbreak* peut avoir été classée à tort comme une injection de prompt.
3. **La défense extraite est-elle une véritable contre-mesure ?** Le résumé peut décrire un résultat ou un protocole d'évaluation plutôt qu'une mesure de protection.
4. **Lorsque la défense vaut « null », cette absence est-elle justifiée ?** Autrement dit, le passage d'origine ne propose-t-il effectivement aucune défense ?

La revue s'est déroulée en deux temps. Un assistant LLM a d'abord proposé, pour chaque cas, une réponse à ces questions accompagnée d'une justification (pré-annotation). Chaque proposition a ensuite été vérifiée par nous-même, en revenant au résumé du cas et, si nécessaire, au passage d'origine. Par exemple, pour un cas issu de l'article de Chao et al. (2023), l'assistant proposait de considérer la valeur « null » comme justifiée, car le passage décrit l'attaque PAIR sans proposer de défense ; ce jugement a été confirmé.

Cette revue a une limite : elle a été réalisée par une seule personne, qui est aussi l'auteure du système, et aucun second annotateur indépendant n'était disponible. Pour en mesurer au moins la cohérence, 30 cas tirés au hasard ont été annotés une seconde fois, sans l'assistant et en suivant un guide de décision écrit, puis comparés à la première revue. Cette comparaison mesure un accord *intra-annotateur* : elle indique si la revue est reproductible par la même personne, mais elle ne garantit pas l'absence de biais.

La revue sert trois usages dans la suite du chapitre : mesurer l'exactitude de la classification, juger si un cas retrouvé est pertinent pour une requête et construire la base révisée de 108 cas.

**Requêtes d'attaque.** Pour évaluer la recherche de cas et les recommandations, nous avons rédigé 18 requêtes. Une requête est une courte description d'attaque en texte libre, semblable à ce qu'un analyste pourrait soumettre à CARL, accompagnée de la technique ATLAS que nous lui avons attribuée manuellement. Par exemple : « une page web consultée par l'assistant contient des instructions cachées qui lui font envoyer la conversation de l'utilisateur vers une adresse contrôlée par l'attaquant » (injection de prompt indirecte). Toutes les requêtes ont été rédigées **avant d'examiner le contenu de la base**, afin de ne pas les formuler, même involontairement, de manière à retrouver des cas existants. Elles sont de deux types.

- **14 requêtes couvertes par le corpus.** Elles portent sur des techniques pour lesquelles la base contient des cas : injection de prompt indirecte (par une page web, un courriel ou un document), injection directe, injection déclenchée, *jailbreak* (jeu de rôle, mode développeur, encodage), infiltration par une application publique, empoisonnement des données d'entraînement et extraction du prompt système. Pour ces requêtes, CARL doit retrouver un cas pertinent et proposer une défense.
- **4 requêtes hors corpus.** Elles portent sur des attaques que nous avons volontairement exclues du corpus lors de sa constitution. La base ne contient donc, par construction, aucun cas pour ces attaques. Le tableau 5.4 les présente.

*Tableau 5.4 — Attaques des quatre requêtes hors corpus*

| Attaque | Description |
|---|---|
| Inférence d'appartenance | Déterminer si une donnée précise faisait partie des données d'entraînement du modèle |
| Extraction de modèle | Reproduire un modèle en l'interrogeant un grand nombre de fois |
| Extraction de données d'entraînement | Amener le modèle à restituer des données qu'il a mémorisées pendant son entraînement |
| Perturbation adverse d'image | Modifier légèrement une image pour tromper un classifieur |

Ces quatre requêtes jouent le rôle d'exemples négatifs. Pour elles, la réponse attendue de CARL n'est pas une défense, mais le signalement qu'aucun cas de sa base ne couvre l'attaque. Ce signalement repose sur le seuil de similarité θ : si le cas le plus proche obtient un score inférieur à θ, la base est considérée comme ne couvrant pas la requête. Les requêtes hors corpus permettent donc de vérifier si ce seuil distingue réellement une attaque connue de la base d'une attaque inconnue.

**Paires de calibration.** Les seuils du vérificateur causal ne sont pas ajustés sur les requêtes de test. Ils sont calibrés sur la base elle-même, à partir de 20 paires de cas partageant la même technique : le modèle adapte la défense de l'un à l'attaque de l'autre, ce qui fournit des exemples positifs et négatifs.

**Évaluation humaine.** Enfin, 76 recommandations distinctes, tirées des différentes configurations comparées, ont été soumises à deux évaluateurs externes, doctorants, qui ne sont pas impliqués dans le projet.

## 5.2 Protocole expérimental

### 5.2.1 Principe de l'évaluation

L'évaluation ne se limite pas à juger la recommandation finale. Chaque étape de CARL est évaluée séparément, sur les mêmes cas, pour deux raisons. D'une part, une erreur commise au début du pipeline peut rester invisible à la fin : une recommandation peut être bien formée et citer un cas, alors que ce cas a été mal classé deux étapes plus tôt. D'autre part, chaque mécanisme de contrôle de CARL vérifie une propriété facile à mesurer, qui n'est pas exactement la propriété recherchée. L'évaluation compare donc, à chaque étape, ce que le mécanisme vérifie et ce qu'il est censé garantir.

Trois questions de recherche structurent cette comparaison, une par mécanisme de contrôle :

- **RQ1 — Classification.** Un identifiant MITRE ATLAS *valide* est-il aussi *correct* ? La validation garantit que l'identifiant existe et concerne les LLM ; la question est de savoir s'il désigne la bonne technique.
- **RQ2 — Recherche de cas.** Le cas le plus *proche* est-il vraiment un cas *pertinent* ? Le seuil de similarité est censé indiquer que la base couvre l'attaque ; la question est de savoir s'il le fait réellement.
- **RQ3 — Vérification des recommandations.** Une défense qui *cite* un cas est-elle une *bonne* défense ? La vérification garantit qu'une mesure est rattachée à un cas ; la question est de savoir si elle protège contre l'attaque.

L'extraction des entités, qui précède ces trois étapes, est évaluée en premier, car elle fournit le contexte de tout le reste du pipeline. Une évaluation humaine complète enfin les mesures automatiques.

### 5.2.2 Mesures utilisées à chaque étape

Le tableau 5.5 récapitule, pour chaque étape, le jeu de données, ce qui est comparé et les mesures utilisées.

*Tableau 5.5 — Protocole d'évaluation par étape*

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

*Tableau 5.6 — Comparaison des extracteurs de la couche 1 sur l'annotation manuelle (45 entités) (rapporté)*

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

*Tableau 5.7 — Contribution de chaque filtre (Mistral-7B, variante thématique) (rapporté)*

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

Deux conséquences en découlent. D'une part, la précision absolue de toutes les méthodes du tableau 5.6 est sous-estimée. D'autre part, le classement des méthodes ne reste valable que si la part d'entités valides non annotées est comparable d'une méthode à l'autre, ce qui n'a pas été vérifié. C'est une raison supplémentaire de fonder le choix de GLiNER sur l'absence d'hallucination plutôt que sur le F1. Ces résultats portent enfin sur un seul article et une seule configuration.

## 5.4 Classification : validité et exactitude (RQ1)

### 5.4.1 Question de recherche

**Un identifiant MITRE ATLAS validé par CARL désigne-t-il réellement la bonne technique d'attaque ?**

### 5.4.2 Objectif de l'expérience

La validation de CARL vérifie qu'un identifiant existe dans MITRE ATLAS et qu'il concerne les LLM. Elle ne vérifie pas qu'il correspond à l'attaque décrite. L'expérience mesure l'écart entre ces deux propriétés, en comparant les identifiants validés à la revue manuelle des cas.

### 5.4.3 Résultats de la classification

*Tableau 5.8 — Validité et exactitude de la classification (rapporté ; intervalles de Wilson à 95 %)*

| Mesure | Résultat | Intervalle |
|---|---|---|
| Identifiants valides | 107 / 119 = 89,9 % | n.r. |
| Identifiants corrects parmi les valides | 47 / 99 = 47,5 % | 37,9 %–57,2 % |
| Défenses qui sont de vraies contre-mesures | 53 / 86 = 61,6 % | 51,1 %–71,2 % |
| Valeurs « null » justifiées | 21 / 22 = 95,5 % | 78,2 %–99,2 % |
| Abstentions justifiées | 0 / 9 | n.r. |

Près de 90 % des identifiants sont valides, mais moins de la moitié des identifiants validés sont corrects. Les valeurs « null » sont fiables, alors qu'aucune abstention n'était justifiée.

### 5.4.4 Analyse des erreurs

Les erreurs ne sont pas aléatoires : 27 des 52 erreurs concernent le *jailbreak* (AML.T0054), classé le plus souvent comme une injection de prompt. Le modèle confond ces deux techniques, qui consistent toutes deux à faire suivre au modèle des instructions malveillantes. Donner au modèle les définitions officielles d'ATLAS ne corrige pas cette confusion : l'exactitude baisse à 41,1 % et 39,8 %, contre 47,5 % sans définitions.

### 5.4.5 Discussion des résultats

La validation apporte une garantie réelle mais limitée : elle empêche les identifiants inventés ou hors sujet, sans garantir la bonne technique. Un identifiant valide n'est correct qu'environ une fois sur deux. Ces taux reposent sur une revue faite par une seule personne (kappa intra-annotateur de 0,62 pour la technique et de 0,75 pour la défense) ; ils doivent être lus comme des bornes supérieures.

Cette erreur ne reste pas dans la classification : la recherche de cas filtre les candidats par technique, donc un cas mal classé peut être écarté d'une requête à laquelle il répondait. RQ2 mesure ce coût.

## 5.5 Recherche de cas : similarité et couverture (RQ2)

### 5.5.1 Question de recherche

**Le cas le plus proche retrouvé par CARL est-il vraiment un cas pertinent, et le seuil θ indique-t-il correctement quand la base ne couvre pas une attaque ?**

### 5.5.2 Objectif de l'expérience

Le seuil θ est censé garantir deux choses : que le meilleur cas retrouvé est pertinent, et que la base couvre bien l'attaque. L'expérience vérifie ces deux points sur les 18 requêtes. Elle compare aussi la base construite à la base révisée, pour mesurer ce que les erreurs de classification de RQ1 coûtent à la recherche.

### 5.5.3 Résultats de la recherche

*Tableau 5.9 — Recherche sur les 14 requêtes couvertes : base construite et base révisée (rapporté)*

| Configuration | Hit@1 (construite) | Hit@3 (construite) | MRR (construite) | Hit@1 (révisée) | Hit@3 (révisée) | MRR (révisée) |
|---|---|---|---|---|---|---|
| Similarité seule (α = 0) | 0,571 | 0,714 | 0,695 | 0,571 | 0,714 | 0,695 |
| Bonus α = 0,05 | 0,571 | 0,857 | 0,707 | 0,786 | 0,857 | 0,843 |
| Filtre par technique (retenu) | 0,571 | 0,786 | 0,716 | **1,000** | **1,000** | **1,000** |

Sur la base construite, le premier cas retrouvé est pertinent pour 57,1 % des requêtes, quelle que soit la configuration. Sur la base révisée, le filtre par technique atteint 100 %. L'écart de 43 points en Hit@1 est la seule différence que les intervalles de confiance permettent d'affirmer.

Pour le seuil θ, la similarité du meilleur cas ne sépare pas les deux groupes de requêtes : trois des quatre requêtes hors corpus atteignent une similarité de 0,689 à 0,747, supérieure à celle de plusieurs requêtes couvertes (0,617 à 0,683). Le meilleur seuil possible (θ = 0,75) n'atteint qu'une exactitude équilibrée de 0,68 ; le seuil retenu (θ = 0,6) atteint 0,63.

### 5.5.4 Analyse des erreurs

Sur la base construite, le filtre par technique n'améliore pas le premier cas retrouvé, car il favorise les cas mal classés autant que les cas pertinents. Une fois les techniques corrigées, le même filtre devient parfait. Le point faible n'est donc pas le mécanisme de recherche, mais la classification de la couche 2 : l'erreur mesurée en RQ1 se transmet directement à la recherche.

Le seuil échoue pour une autre raison. Le corpus étant consacré aux attaques contre les LLM, toute requête qui décrit une attaque de ce type trouve un cas qui lui ressemble, même si la base ne contient pas cette attaque.

### 5.5.5 Discussion des résultats

Un cas proche n'est pas forcément un cas pertinent, et une similarité élevée ne prouve pas que la base couvre l'attaque. Le seuil θ ne détecte que les requêtes clairement étrangères au domaine, et non les attaques plausibles absentes de la base, alors que c'est précisément dans ce cas qu'un signal de couverture serait utile. La borne de la base révisée est par ailleurs optimiste, car les techniques des requêtes et des cas révisés ont été attribuées par la même personne. RQ3 mesure ce que ces deux erreurs coûtent aux recommandations.

## 5.6 Adaptation et recommandations : traçabilité et solidité (RQ3)

### 5.6.1 Question de recherche

**Une recommandation qui cite un cas, et passe donc la vérification, est-elle vraiment une bonne défense ?**

### 5.6.2 Objectif de l'expérience

La vérification garantit qu'une mesure est rattachée à un cas retrouvé. L'expérience compare plusieurs façons de produire et de vérifier les recommandations, afin de voir ce que cette garantie apporte réellement : génération sans recherche, recherche sans vérification, boucle avec la règle lexicale, juge LLM utilisant le même modèle, boucle de type Self-Refine, et notre boucle avec le vérificateur causal aux seuils calibrés. Les résultats portent sur 13 requêtes couvertes : la requête sur l'extraction du prompt système, marquée hors corpus dans le fichier de requêtes, est exclue des deux groupes.

### 5.6.3 Résultats

*Tableau 5.10 — Qualité des recommandations sur la base construite (rapporté)*

| Configuration | Recommandations (requêtes servies) | Ancrage | Adaptation | Adéquation causale | Hors corpus |
|---|---|---|---|---|---|
| Sans recherche | 39 (13) | 0,00 | 0,56 | — | 12 |
| Recherche sans vérification | 38 (13) | 0,42 | 0,69 | 0,74 | 6 |
| Boucle, règle lexicale | 17 (9) | 1,00 | — | — | 2 |
| Boucle, juge LLM | 29 (12) | 1,00 | 0,69 | 0,76 | 4 |
| Self-Refine (même modèle) | 39 (13) | 0,13 | 0,67 | 0,62 | 6 |
| **Boucle, vérificateur causal calibré (CARL)** | **9 (7)** | **1,00** | **0,89** | **1,00** | **0** |
| Base révisée (borne supérieure) | 11 (9) | 1,00 | 1,00 | 1,00 | 4 |

*Hors corpus : nombre de recommandations renvoyées pour les quatre requêtes non couvertes, qui devrait être nul.*

Sans recherche, aucune recommandation n'est ancrée, et le modèle en propose douze pour des attaques que la base ne documente pas. La recherche seule fait monter l'ancrage à 0,42. Toutes les boucles atteignent un ancrage de 1,00. Notre configuration sert 7 des 13 requêtes, avec des mesures toutes causalement adéquates, et ne renvoie aucune recommandation hors corpus.

### 5.6.4 Analyse des erreurs

L'ancrage de 1,00 est obtenu par construction : les recommandations non traçables sont supprimées. Il ne prouve donc pas que les mesures sont bonnes. Deux mécanismes le gonflent :

- **la règle lexicale récompense la copie** : exiger 60 % de mots communs avec la défense citée favorise la reprise mot pour mot plutôt que l'adaptation ;
- **la traçabilité hérite des erreurs des cas** : pour un *jailbreak* caché dans une requête encodée en Base64, la boucle accepte « une revue régulière du code », copiée d'un cas décrivant un ver qui se propage entre applications, que le pipeline avait mal classé comme *jailbreak*. La recommandation est parfaitement traçable, mais elle ne répond pas à l'attaque.

Le vérificateur causal supprime ces copies, mais au prix de la couverture : avec les seuils fixés a priori, il ne sert que 3 requêtes ; avec les seuils calibrés (0,627 et 0,534), il en sert 7. Le seuil sémantique reste peu discriminant (exactitude équilibrée de 0,63). À l'inverse, les approches où le modèle se juge lui-même acceptent presque tout : la critique de Self-Refine a approuvé le plan initial pour les 16 requêtes avec des cas retrouvés, si bien que seulement 13 % de ses recommandations sont ancrées. Enfin, une révision (N = 1) fait passer le nombre de requêtes servies de 4 à 9 ; les révisions suivantes coûtent environ cinq fois plus d'appels par requête gagnée.

### 5.6.5 Discussion des résultats

Une recommandation traçable n'est pas forcément une bonne défense : un vérificateur qui contrôle le lien entre une mesure et sa source ne peut pas détecter que la source est fausse, ni qu'elle répond à une autre attaque. Le vérificateur causal réduit cet écart sans le combler, et il reste dépendant des deux étapes précédentes : sur la base révisée, la boucle accepte quatre recommandations hors corpus, parce que le seuil θ ne signale pas l'absence de couverture. La vérification hors du modèle reste néanmoins préférable à l'auto-vérification, qui approuve ce qu'elle a produit au lieu de le contrôler.
