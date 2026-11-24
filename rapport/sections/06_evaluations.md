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

### 5.2.2 Configuration expérimentale

Toutes les expériences utilisent la même configuration, décrite au chapitre 4 :

- la **base construite** de 119 cas, telle que le pipeline l'a produite, sans correction manuelle ; la base révisée de 108 cas sert uniquement de borne supérieure ;
- GLiNER (`urchade/gliner_multi-v2.1`, seuil de confiance 0,4) pour la couche 1, et Mistral-7B-Instruct-v0.3, servi par Ollama avec une température de 0,1, pour la couche 2, la proposition et la révision ;
- `nomic-embed-text` pour les plongements lexicaux ;
- une recherche limitée aux cas de la technique de la requête, avec un bonus α = 0,05, k = 3 cas retournés et un seuil θ = 0,6 ;
- le niveau de recherche secondaire désactivé : aucun article n'est ajouté à la base pendant les expériences.

### 5.2.3 Mesures utilisées à chaque étape

Le tableau 5.5 récapitule, pour chaque étape, le jeu de données, ce qui est comparé et les mesures utilisées.

*Tableau 5.5 — Protocole d'évaluation par étape*

| Étape | Jeu de données | Ce qui est comparé | Mesures |
|---|---|---|---|
| Extraction des entités | 45 entités annotées | GLiNER et Mistral-7B guidé par prompt ; effet de chaque filtre | Précision, rappel, F1, taux d'hallucination |
| RQ1 — Classification | Revue des 119 cas | Identifiant valide et identifiant correct | Taux de validité, taux d'exactitude, fiabilité des « null » et des abstentions, accord intra-annotateur |
| RQ2 — Recherche | 18 requêtes | Base construite et base révisée ; requêtes couvertes et hors corpus | Hit@1, Hit@3, MRR, similarité du meilleur cas |
| RQ3 — Recommandations | 18 requêtes, 20 paires de calibration | Génération sans recherche, recherche sans vérification, boucle avec vérification, variantes du vérificateur | Ancrage, taux d'hallucination, adaptation, adéquation causale, part des requêtes servies |
| Évaluation humaine | 76 recommandations | Les configurations de RQ3 | Échelles de 1 à 5, accord entre évaluateurs |

**Extraction.** Les entités extraites sont comparées aux 45 entités annotées. Une entité extraite est considérée comme correcte si son texte correspond à une entité annotée, après normalisation des caractères, de la casse et de la ponctuation, avec un taux de ressemblance d'au moins 0,85. La **précision** est la part des entités extraites qui sont correctes ; le **rappel** est la part des entités annotées qui ont été retrouvées ; le **F1** est la moyenne harmonique des deux. Le **taux d'hallucination** est la part des entités extraites qui n'apparaissent pas dans le texte de l'article. Pour mesurer l'apport de chaque filtre, les filtres sont appliqués un par un aux mêmes sorties enregistrées du modèle, ce qui isole leur effet de la variabilité de la génération.

**Classification (RQ1).** Deux taux sont comparés. Le **taux de validité** est la part des cas dont l'identifiant a passé les deux contrôles de validation. Le **taux d'exactitude** est la part de ces identifiants que la revue juge corrects. Les mêmes comparaisons sont faites pour les défenses (part des défenses extraites qui sont de vraies contre-mesures), pour les valeurs « null » et pour les abstentions. Chaque taux est accompagné d'un intervalle de confiance à 95 % de Wilson, adapté aux proportions calculées sur de petits effectifs. La cohérence de la revue est mesurée par le **kappa de Cohen** entre la première annotation et la réannotation de 30 cas : il vaut 1 pour un accord parfait et 0 pour un accord dû au hasard.

**Recherche (RQ2).** Pour chaque requête couverte, on regarde si les cas retrouvés sont pertinents, c'est-à-dire si leur technique, telle que la revue l'a établie, fait partie des techniques attendues pour la requête. Le **Hit@1** est la part des requêtes pour lesquelles le premier cas retrouvé est pertinent ; le **Hit@3** est la part des requêtes pour lesquelles au moins un des trois cas retrouvés l'est ; le **MRR** (*Mean Reciprocal Rank*) récompense un cas pertinent d'autant plus qu'il apparaît tôt dans la liste. Ces mesures sont calculées sur la base construite et sur la base révisée, ce qui permet de mesurer ce que coûtent les erreurs de classification. Pour évaluer le seuil θ, on compare enfin la similarité du meilleur cas pour les requêtes couvertes et pour les requêtes hors corpus.

**Recommandations (RQ3).** Trois configurations sont comparées : (1) la génération sans recherche, où le modèle ne voit que la description de l'attaque ; (2) la génération à partir des trois cas retrouvés, sans vérification ; (3) la boucle « proposer, vérifier, réviser » avec une révision. La boucle est testée avec plusieurs vérificateurs : la règle lexicale, la règle causale, la règle causale avec les seuils calibrés, un juge LLM utilisant le même modèle, et une boucle de type Self-Refine où le modèle critique sa propre réponse. Les mesures sont :

- l'**ancrage** : part des recommandations finales qui satisfont la règle de traçabilité, c'est-à-dire qui citent un cas retrouvé dont la défense n'est pas « null » et dont elles sont suffisamment proches ;
- le **taux d'hallucination** : une mesure légère, propre au domaine, inspirée des outils d'évaluation de la fidélité aux sources (Es et al., 2024 ; Tang et al., 2024) ; ce n'est pas un instrument validé ;
- l'**adaptation** : part des mesures qui mentionnent un élément de la nouvelle attaque absent de la défense citée ;
- l'**adéquation causale** : part des mesures qui visent un maillon existant de la chaîne causale et lui sont proches ;
- la **part des requêtes servies** : part des requêtes couvertes qui reçoivent au moins une recommandation ;
- le nombre de recommandations renvoyées sur les requêtes hors corpus, qui devrait être nul.

Les seuils du vérificateur causal sont calibrés sur les 20 paires de cas en maximisant l'indice de Youden, qui cherche le meilleur compromis entre les exemples positifs acceptés et les exemples négatifs rejetés.

**Évaluation humaine.** Chaque recommandation est notée de 1 à 5 sur trois critères : utilité, solidité et applicabilité, avec en plus un jugement binaire « j'appliquerais cette mesure ». Les évaluateurs voient la description de l'attaque, la recommandation et la défense citée, dans un ordre aléatoire et sans savoir de quelle configuration elle provient. L'accord entre les deux évaluateurs est mesuré par l'**alpha de Krippendorff**, qui vaut 1 pour un accord parfait, 0 pour un accord dû au hasard, et devient négatif lorsque le désaccord dépasse le hasard.

**Incertitude.** Pour les mesures calculées sur les requêtes, des intervalles de confiance à 95 % sont estimés par *bootstrap* : les requêtes sont tirées au hasard avec remise 10 000 fois, et la mesure est recalculée à chaque tirage. Avec 14 requêtes couvertes, ces intervalles sont larges, ce qui est pris en compte dans l'interprétation des résultats.

## 5.3 Extraction des entités

Cette étape compare les deux méthodes envisagées pour la couche 1 : GLiNER, qui sélectionne des segments du texte, et Mistral-7B guidé par un prompt, qui génère les entités, complété par les quatre filtres décrits au chapitre 4.

**Choix de l'extracteur.** Sur l'article annoté, GLiNER obtient un F1 de 0,292, contre 0,192 pour Mistral-7B avec ses filtres, et aucune des entités qu'il extrait n'est absente du texte. Ce second point est déterminant : la sortie de la couche 1 sert de contexte à la couche 2, et une entité inventée à ce stade serait transmise à toutes les étapes suivantes. GLiNER a donc été retenu pour la couche 1.

**Contribution des filtres.** Les filtres ont été évalués sur Mistral-7B, la méthode qui en a besoin. Le tableau 5.6 résume leur effet.

*Tableau 5.6 — Effet des filtres sur l'extraction par Mistral-7B (rapporté)*

| Filtre | Effet mesuré |
|---|---|
| Longueur maximale | Retire 54 prédictions, surtout des propositions descriptives ; la précision passe de 0,089 à 0,116, sans perte d'entité correcte |
| Liste blanche d'étiquettes | Seul filtre avec un compromis : il écarte deux entités correctes extraites sous une étiquette hors taxonomie ; le rappel passe de 0,511 à 0,467 |
| Fuite de l'exemple | Aucun effet sur cet article ; filtre de sécurité contre une erreur observée sur un corpus antérieur |
| Valeurs de remplissage | Aucun effet sur cet article ; même rôle de sécurité |
| Ensemble des filtres | Le F1 passe de 0,143 à 0,192 (+34 %) |

Le taux d'hallucination semble augmenter, de 0,011 à 0,017, mais il s'agit d'un effet de dénominateur : les trois mêmes entités non présentes dans le texte restent, parmi un nombre plus faible de prédictions.

**Limite de l'annotation.** Les précisions sont faibles pour les deux méthodes, mais elles sous-estiment en partie la qualité réelle de l'extraction. Un contrôle de 30 faux positifs tirés au hasard a montré que 17 d'entre eux (57 % ; intervalle de Wilson 39 %–73 %) étaient de vraies entités de l'article, que l'annotation avait omises : types d'applications, impacts cités dans la taxonomie propre à l'article, ou défense proposée. Les 13 autres étaient des segments descriptifs. L'annotation de référence est donc incomplète, et les scores doivent être lus comme des comparaisons entre méthodes plutôt que comme des valeurs absolues. Ces résultats portent en outre sur un seul article et une seule configuration.

## 5.4 Classification : validité et exactitude (RQ1)

La première question de recherche porte sur l'ancrage dans MITRE ATLAS : un identifiant qui passe la validation désigne-t-il la bonne technique ?

### 5.4.1 Écart entre validité et exactitude

Le tableau 5.7 met en regard ce que la validation garantit et ce que la revue mesure.

*Tableau 5.7 — Validité et exactitude de la classification (rapporté ; intervalles de Wilson à 95 %)*

| Mesure | Résultat | Intervalle |
|---|---|---|
| Identifiants valides (base construite) | 107 / 119 = 89,9 % | n.r. |
| Identifiants corrects parmi les valides (cas retenus) | 47 / 99 = 47,5 % | 37,9 %–57,2 % |
| Défenses extraites qui sont de vraies contre-mesures | 53 / 86 = 61,6 % | 51,1 %–71,2 % |
| Valeurs « null » justifiées | 21 / 22 = 95,5 % | 78,2 %–99,2 % |
| Abstentions justifiées | 0 / 9 | n.r. |

Les deux premières lignes doivent être lues ensemble. Près de 90 % des identifiants passent la validation, mais moins de la moitié des identifiants validés désignent la bonne technique. La validation remplit bien son rôle : elle écarte les identifiants inventés et ceux qui ne concernent pas les LLM. Mais un identifiant valide n'est correct qu'environ une fois sur deux. Le mécanisme garantit donc à peu près la moitié de ce qu'on attend de lui.

Les trois autres lignes nuancent ce constat :

- **les défenses** : environ six défenses extraites sur dix sont de vraies contre-mesures ; les autres rapportent un résultat d'expérience, reformulent la procédure de l'attaque ou décrivent le protocole d'évaluation des auteurs ;
- **les valeurs « null »** sont fiables : lorsque CARL indique qu'un passage ne propose aucune défense, c'est exact dans 21 cas sur 22. Le choix d'enregistrer explicitement l'absence de défense, plutôt que de laisser le modèle la combler, est donc justifié ;
- **les abstentions** ne le sont pas : pour aucun des 9 cas sans identifiant l'abstention n'était justifiée, car une technique de la liste s'appliquait à chaque fois. Le modèle s'abstient donc dans des cas où il aurait dû répondre.

### 5.4.2 Nature des erreurs

Les erreurs de classification ne sont pas aléatoires. Sur les 52 identifiants incorrects, 27 concernent un cas dont la bonne technique est le *jailbreak* (AML.T0054) ; 22 d'entre eux ont été classés à la place comme une injection de prompt ou comme AML.T0093 (infiltration par une application publique). La sous-technique « injection déclenchée » (AML.T0051.002) n'était correcte que dans 1 de ses 17 utilisations. Comme AML.T0054 fait partie de la liste des techniques candidates, la restriction de la liste n'est pas en cause : la bonne réponse était disponible, mais le modèle ne l'a pas choisie.

Le modèle confond donc surtout des techniques voisines : le *jailbreak*, qui vise les protections du modèle lui-même, et l'injection de prompt, qui détourne les instructions d'une application. Ces deux attaques se ressemblent dans leur formulation, car toutes deux consistent à faire suivre au modèle des instructions malveillantes.

### 5.4.3 Les définitions n'aident pas le modèle

Pour savoir si le modèle manquait d'information, chaque cas a été reclassé à partir de son passage d'origine, avec un prompt consacré uniquement à la classification, dans deux variantes : avec les seuls noms des techniques, puis avec la définition officielle de chaque technique ATLAS et une règle explicite distinguant *jailbreak*, injection de prompt et empoisonnement des données. Aucune variante n'améliore le résultat initial : 41,1 % et 39,8 % des identifiants validés sont corrects, contre 47,5 % pour la couche 2. Avec les définitions, le modèle se replie surtout sur la technique parente AML.T0051. Comme la règle de distinction a été rédigée après avoir observé ces erreurs, ce résultat négatif est même optimiste.

Restreindre la liste des techniques apporte donc une garantie réelle mais limitée : elle empêche les identifiants inventés ou hors sujet, sans permettre à un modèle de 7 milliards de paramètres de séparer des techniques proches.

### 5.4.4 Cohérence de la revue

Ces taux reposent sur une revue réalisée par une seule personne. La réannotation de 30 cas donne un kappa de Cohen de 0,62 pour la technique (accord sur 16 des 22 cas conservés dans les deux annotations) et de 0,75 pour le statut de la défense (14 sur 16). L'accord est plus faible sur la question de savoir si un enregistrement décrit une attaque (24 sur 30, kappa de 0,30) : la réannotation a retiré sept enregistrements, surtout des énoncés généraux ou des résultats, que la première revue avait conservés.

Les 14 désaccords ont été tranchés en revenant au passage d'origine ; la réannotation a été retenue dans 12 cas. Sur cet échantillon, la première revue, réalisée avec l'assistant LLM, se montre trop indulgente : elle conserve des énoncés généraux comme des attaques (cinq cas) et choisit une sous-technique là où le résumé ne justifie que la technique parente (trois cas). Les taux du tableau 5.7 surestiment donc la part de cas exploitables et doivent être lus comme des **bornes supérieures**. Comme les deux annotations proviennent de la même personne, ce kappa mesure la reproductibilité de la revue, mais pas son biais ; une annotation indépendante reste nécessaire.

### 5.4.5 Réponse à RQ1

Un identifiant ATLAS valide n'est pas, en général, un identifiant correct : 89,9 % des identifiants sont valides, mais seulement 47,5 % des identifiants validés sont corrects. L'écart n'est pas dû au hasard : il vient surtout de la confusion entre *jailbreak* et injection de prompt, que ni la restriction de la liste ni les définitions officielles ne corrigent. À l'inverse, l'enregistrement explicite des valeurs « null » se révèle fiable.

Cette erreur ne reste pas confinée à la classification. La recherche de cas filtre les candidats par technique : un cas mal classé peut donc être écarté d'une requête à laquelle il répondait, ou proposé à une requête à laquelle il ne répond pas. La question de recherche suivante mesure ce que cette erreur coûte à la recherche des cas.
