# Chapitre 5 — Évaluations

Ce chapitre évalue CARL étape par étape. Il présente d'abord les données utilisées : le corpus d'articles, la base de cas construite à partir de ce corpus et les jeux de données de test (section 5.1). Il décrit ensuite le protocole expérimental, puis les résultats de chaque étape.

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
3. *Exclure volontairement certaines attaques.* Aucun article ne porte sur l'inférence d'appartenance, l'extraction de modèle, l'extraction de données d'entraînement ou les exemples adverses sur des images. Ces attaques sont réservées aux requêtes de test hors corpus (section 5.1.3) : elles servent à vérifier si CARL signale correctement qu'aucun cas de sa base ne couvre une attaque. Les inclure dans le corpus supprimerait ces exemples négatifs.

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

**Base révisée.** Les 119 cas ont ensuite été relus un par un (section 5.1.3). Cette revue a conduit à une seconde version de la base, dite *révisée* : 11 enregistrements qui ne décrivent pas une attaque ont été retirés, les identifiants erronés ont été corrigés, et les défenses qui ne sont pas de véritables contre-mesures ont été remplacées par « null ». Elle compte 108 cas, dont 84 concernent le *jailbreak* ou l'injection de prompt. Cette base révisée n'est jamais utilisée comme base de travail : elle sert seulement de **borne supérieure**, pour estimer ce qu'obtiendrait CARL si sa classification était sans erreur.

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

Cette revue a une limite : elle a été réalisée par une seule personne, qui est aussi l'auteure du système, et aucun second annotateur indépendant n'était disponible. Pour en mesurer au moins la cohérence, 30 cas tirés au hasard ont été annotés une seconde fois, sans l'assistant et en suivant un guide de décision écrit, puis comparés à la première revue. Cette comparaison mesure un accord *intra-annotateur* (section 5.4) : elle indique si la revue est reproductible par la même personne, mais elle ne garantit pas l'absence de biais.

La revue sert trois usages dans la suite du chapitre : mesurer l'exactitude de la classification (section 5.4), juger si un cas retrouvé est pertinent pour une requête (section 5.5) et construire la base révisée de 108 cas (section 5.1.2).

**Requêtes d'attaque.** Pour évaluer la recherche de cas et les recommandations, nous avons rédigé 18 requêtes. Une requête est une courte description d'attaque en texte libre, semblable à ce qu'un analyste pourrait soumettre à CARL, accompagnée de la technique ATLAS que nous lui avons attribuée manuellement. Par exemple : « une page web consultée par l'assistant contient des instructions cachées qui lui font envoyer la conversation de l'utilisateur vers une adresse contrôlée par l'attaquant » (injection de prompt indirecte). Toutes les requêtes ont été rédigées **avant d'examiner le contenu de la base**, afin de ne pas les formuler, même involontairement, de manière à retrouver des cas existants. Elles sont de deux types.

- **14 requêtes couvertes par le corpus.** Elles portent sur des techniques pour lesquelles la base contient des cas : injection de prompt indirecte (par une page web, un courriel ou un document), injection directe, injection déclenchée, *jailbreak* (jeu de rôle, mode développeur, encodage), infiltration par une application publique, empoisonnement des données d'entraînement et extraction du prompt système. Pour ces requêtes, CARL doit retrouver un cas pertinent et proposer une défense.
- **4 requêtes hors corpus.** Elles portent sur des attaques que nous avons volontairement exclues du corpus lors de sa constitution (section 5.1.1). La base ne contient donc, par construction, aucun cas pour ces attaques. Le tableau 5.4 les présente.

*Tableau 5.4 — Attaques des quatre requêtes hors corpus*

| Attaque | Description |
|---|---|
| Inférence d'appartenance | Déterminer si une donnée précise faisait partie des données d'entraînement du modèle |
| Extraction de modèle | Reproduire un modèle en l'interrogeant un grand nombre de fois |
| Extraction de données d'entraînement | Amener le modèle à restituer des données qu'il a mémorisées pendant son entraînement |
| Perturbation adverse d'image | Modifier légèrement une image pour tromper un classifieur |

Ces quatre requêtes jouent le rôle d'exemples négatifs. Pour elles, la réponse attendue de CARL n'est pas une défense, mais le signalement qu'aucun cas de sa base ne couvre l'attaque. Ce signalement repose sur le seuil de similarité θ : si le cas le plus proche obtient un score inférieur à θ, la base est considérée comme ne couvrant pas la requête. Les requêtes hors corpus permettent donc de vérifier si ce seuil distingue réellement une attaque connue de la base d'une attaque inconnue (section 5.5).

**Paires de calibration.** Les seuils du vérificateur causal ne sont pas ajustés sur les requêtes de test. Ils sont calibrés sur la base elle-même, à partir de 20 paires de cas partageant la même technique : le modèle adapte la défense de l'un à l'attaque de l'autre, ce qui fournit des exemples positifs et négatifs (section 5.6).

**Évaluation humaine.** Enfin, 76 recommandations distinctes, tirées des différentes configurations comparées, ont été soumises à deux évaluateurs externes, doctorants, qui ne sont pas impliqués dans le projet (section 5.7).
