
# Task-Preserving Graph Compression for Agent Working Memory

## 1. 核心研究问题

**给定一段工具执行历史，能否学习对显式工作记忆图进行受约束删改，在固定 agent、后续任务性能损失不超过预设容忍度的条件下，比强文本压缩及同等任务监督的无图选择实现更低的端到端总成本？**

核心不是预设“图比文本更紧凑”，而是检验：**图所定义的编辑约束，是否改善任务监督下的压缩决策。**

## 2. 创新定位与现有工作的区别

**本研究拟提出“语义约束下的图删改＋续段执行监督的累计风险学习”：结构规则限定可以怎样改，风险模型判断改后整份记忆是否仍能支持后续任务。** 两者共同构成方法主张，而不是分别宣称“使用图”或“使用任务反馈”本身具有新颖性。

### 2.1 两项相互配合的方法创新

**（1）面向任务保持的状态级图编辑空间。** 将对象、事实、执行结果和约束表示为显式图，通过删除、字段投影和过程折叠压缩记忆。编辑规则要求保留解释剩余信息所需的对象绑定、时间或版本、来源与适用范围；已完成的过程可以被有可见证据支持的结果替代，不产生未经观察的新结论。优化对象是支持后续执行的工作记忆，而不是可还原的历史记录或可复用技能程序。

**（2）由配对续段执行监督的累计图删改风险学习。** 从相同断点与环境状态继续执行，始终以原始完整历史为参照，利用已有任务评分器为候选图生成监督。学习器以原始候选图、当前压缩图和候选编辑为条件，预测“完整历史成功的运行中，编辑后整份记忆对应的续段失败比例”，据此选择具体编辑。**累计风险评价的是经过已有删改后的整份记忆，不是单个节点的固定重要性，也不是各次编辑风险之和。** 部署时不访问未来请求或 GT，也不回放未来任务。

### 2.2 与最相关工作的具体差异

以下比较针对所引论文版本的主要机制；现有工作并非完全不使用执行反馈、上下文相关效用或图重写。

| 相关工作 | 已有工作与本研究的差异 |
|---|---|
| **[ACON][6]** | 通过执行反馈优化文本压缩指南，但未将具体合法图编辑作为风险学习与选择的对象；本研究拟预测编辑后整份记忆的任务破坏风险，并据此选择删改操作。 |
| **[ContextWeaver][9]** | 通过步骤依赖图选择和组织历史，但未以续段任务反馈学习状态与字段级的删改；本研究拟学习删除、字段投影和过程折叠，保留后续执行所需信息。 |
| **[Decision-Aware Memory Cards / CICL][8]** | 根据上下文相关效用选择内容，但未以完整历史为固定参照学习连续删改后的整图任务风险；本研究拟通过配对续段回放学习该累计风险，并据此选择编辑。 |
| **[SkillZip][10]** | 将重复技能过程压缩为可逆宏，但未以任务续段表现为标准学习哪些历史细节可以丢弃；本研究拟学习无需还原原过程、以任务保持为目标的有损工作记忆图删改。 |

### 2.3 创新边界

贡献集中于上述**编辑空间、监督目标与选择机制的结合**。固定 LLM、轻量 MLP、使用已有任务 GT 和报告总成本是研究设置或评价要求，不另列为独立创新。合法性检查不保证任务成功，风险预测也不构成性能保持证明；优势须在匹配可见信息、任务监督和预算的对照实验中建立，不预先宣称优于现有方法或拥有全领域“首次”优先权。

## 3. 研究范围

固定 agent 的 LLM、工具接口和执行策略，每个训练样本只进行一次压缩，但断点在不同任务的**中段或后半程合法位置采样**，排除任务已经完成或只剩收尾回复的位置。  
只研究“给定当前工作记忆，如何压缩”，不同时学习压缩时机，也不引入跨任务知识积累、多智能体协作或 latent memory。

## 4. 要验证的假设

**显式对象、状态与依赖约束能够缩小不合理的删改空间；基于当前压缩状态学习的累计任务破坏风险能够进一步改进编辑选择。二者结合，相比强文本压缩和同等任务监督的无图选择，应当在匹配后续任务性能时降低总成本。**

该假设需要分别检验“学习相对固定规则”的收益，以及“图约束相对无图选择”的收益；不将图的可读性、节点数量减少或更换编码格式本身当作证据。

## 5. 任务

$$
\boxed{
x_{i,t}
\xrightarrow{\;P\;}
G^0_{i,t}
\xrightarrow{\;C_\theta\;}
\widehat G_{i,t}
\xrightarrow{\;S\;}
M_{i,t}
}
$$

其中，$i$ 表示原始任务，$t$ 表示本样本的压缩断点；$P$ 是固定的历史到候选图抽取器，$G^0_{i,t}$ 是候选图，$C_\theta$ 是待学习的图优化器，$S$ 是固定的图到文本编码，$M_{i,t}$ 是交给 agent 的压缩记忆。

图的节点表示对象、事实、执行结果或约束，边表示对象绑定、依赖或适用关系，属性保存值、时间、版本与来源；**不强制要求图是 DAG，也不强制连通**。

## 6. 输入

$$
\boxed{
x_{i,t}
=
\left(H_{i,\le t},\mathcal T_i\right),
\qquad
H_{i,\le t}=(m_{i,1},\ldots,m_{i,t})
}
$$

$H_{i,\le t}$ 是截至断点的可见历史，包含用户请求、助手回复、工具调用及其返回；$\mathcal T_i$ 是当时允许使用的工具说明。当前已知目标包含在历史中，**未来请求、任务 GT 和隐藏环境状态不属于压缩器输入**。

## 7. 输出

$$
\boxed{
\widehat G_{i,t}
=
\left(
\underbrace{V_{i,t}}_{\text{节点}},
\underbrace{E_{i,t}}_{\text{关系}},
\underbrace{\alpha_{i,t}}_{\text{属性与限定}}
\right),
\qquad
M_{i,t}=S(\widehat G_{i,t})
}
$$

## 8. 优化目标

$$
\boxed{
\begin{aligned}
\min_\theta\quad
&\mathbb E_{i,t}\!\left[L(\widehat G_{i,t})\right]\\
\text{s.t.}\quad
&\operatorname{Succ}_{\theta}
\ge
\operatorname{Succ}_{\mathrm{full}}-\varepsilon,\\
&\widehat G_{i,t}\in\mathcal R(G^0_{i,t}),
\end{aligned}
\qquad
L(G)=\left|\operatorname{Tokenizer}_{\pi}(S(G))\right|
}
$$

$L(G)$ 是目标 LLM 实际读取的记忆 token 数，包含节点内容、边和限定条件；$\mathcal R(G^0)$ 是通过允许的合法删改能够得到的图集合；$\varepsilon$ 是预先规定的允许性能损失。

这里寻找的是**固定表示与删改空间内的紧凑图**，不宣称得到所有可能表示中的全局最小图；长度是直接优化目标，是否真正降低总成本则由端到端实验检验。

## 9. 优化器的 Action 范围

$$
\boxed{
\mathcal A_{\mathrm{legal}}(G)
=
\left\{
a\in
\mathcal A_{\mathrm{delete}}
\cup
\mathcal A_{\mathrm{project}}
\cup
\mathcal A_{\mathrm{fold}}
:
\operatorname{Valid}(G,a)=1,\
L(a(G))<L(G)
\right\}
}
$$

$\operatorname{Valid}$ 是程序化合法性检查，验证来源、引用和限定信息是否符合预定义规则，**不等同于保证后续任务成功**。

| Action | 操作内容 | 合法性要求 |
|---|---|---|
| **Delete：删除** | 删除节点、关系或一组冗余信息，如重复目录观察。 | 不能留下悬空引用；删除限定条件时，不能保留被错误扩大适用范围的断言。 |
| **Project：字段投影** | 删除记录中的部分字段，保留需要的内容。 | 保留解释剩余字段所需的对象身份、单位、时间或版本。 |
| **Fold：过程折叠** | 用已确认的结果替代部分执行经过，如用“文件当前位置”替代查找与移动过程。 | 结果必须已有可见证据；只能使用预定义重写规则，不能生成未经观察的新结论。 |

## 10. 定义“任务性能保持”

$$
\boxed{
\begin{aligned}
Y_{i,t}(M;\omega)
&=
\mathcal J_{i,t}\!\left(
\operatorname{Rollout}_{\pi}
(s_{i,t},M,U_{i,>t};\omega)
\right)
\in\{0,1\},\\[2pt]
\operatorname{Succ}_{\theta}
&=
\mathbb E_{i,t,\omega}
\!\left[Y_{i,t}(S(\widehat G_{i,t});\omega)\right]\\
&\ge
\underbrace{
\mathbb E_{i,t,\omega}
\!\left[Y_{i,t}(H_{i,\le t};\omega)\right]
}_{\operatorname{Succ}_{\mathrm{full}}}
-\varepsilon .
\end{aligned}
}
$$

$\pi$ 是固定 agent，$s_{i,t}$ 是恢复后的断点环境状态，$U_{i,>t}$ 是随后逐步提供的用户请求，$\omega$ 表示运行随机性；$\mathcal J_{i,t}$ 根据已有 GT 评价续段，必要时结合共同前缀进行完整验收。

**保持的是后续任务成功能力，不要求生成相同文本或复制相同调用轨迹。** 该定义是任务与断点分布上的性能要求，不是每个样本都绝不失败的保证。

## 11. 数据集和 GT

任务结果采用客观验收，延续原稿中的最终状态、工具调用和环境成功信号，而不是以输出图与某张人工图的相似度为主要标准。[^proposal]

| 数据或材料 | 可以直接得到 | 需要我们构造或手动完成 |
|---|---|---|
| **BFCL Multi-Turn：Base、Long-Context**，用于开发与主实验 | 多轮请求、API 环境、初始配置、人工参考调用轨迹，以及状态和调用结果路径检查；两类各有 200 个任务。参见 [BFCL 官方多轮说明][bfcl-mt]。 | 编写历史采集、断点采样与状态恢复程序；执行前缀获得真实工具返回；建立按任务族划分的训练、开发、测试集。 |
| **AppWorld**，用于外部验证 | 任务、可执行应用环境与程序化状态验收，能够检查任务完成及意外状态改动。参见文献 [2]。 | 适配工具日志和断点恢复；锁定方法后进行验证；遵循官方划分和测试 GT 隔离规则。参见 [AppWorld 官方仓库][appworld-repo]。 |
| **候选图 $G^0$ 与合法动作** | 没有与本研究完全对应的现成图标签。 | **人工设计**图 schema、解析规则和合法重写规则；随后自动构图，并人工抽检对象绑定、版本和来源。 |
| **删改风险标签** | 任务评分器可以复用，但没有现成的删改标签。 | **自动生成**候选删改，回放后续任务，根据已有评分器标记风险；人工只需抽查异常案例。 |
| **“最小图”GT** | 不假定存在唯一标准答案图。 | **不做全量人工标注**；离线搜索结果作为充分候选，小图穷举仅用于诊断最小性。 |

## 12. 比较方法

除基础基线与消融项外，拟比较下列已有方法，在相同 agent、可见历史与断点下评价任务成功率和端到端总成本，并明确区分方法适配与原论文设置。

| 方法 | 核心机制 | 比较重点 | 实验安排 |
|---|---|---|---|
| **[ACON][6]** | 任务反馈优化压缩指南。 | 图删改是否优于任务反馈驱动的文本压缩。 | **主要对比**：保留指南优化机制，适配单次断点压缩，匹配训练任务与反馈预算。 |
| **[ContextWeaver][9]** | 步骤依赖图与祖先选择。 | 状态、事实级删改相对步骤级历史选择的收益。 | **主要适配对比**：将依赖选择机制适配到同一工具历史与压缩断点。 |
| **[Decision-Aware Memory Cards / CICL][8]** | 上下文相关效用排序与记忆卡片装配。 | 整图累计风险学习相对内容单元效用选择的收益。 | **主要适配对比**：候选记忆仅来自当前任务可见历史，匹配监督与预算。 |
| **[SkillZip][10]** | 契约保持的可逆技能宏压缩。 | 任务保持的有损删改与可逆过程压缩的区别。 | **补充机制对照**：仅在可构造同任务适配时开展；不将技能库原结果直接纳入主实验排名。 |

## 13. 如何构造一个样本

$$
\boxed{
\begin{aligned}
\mathcal B_i
&=
\left\{
t\in\mathcal B_i^{\mathrm{legal}}:
\alpha N_i\le t\le\beta N_i,\
r_i(t)\ge r_{\min}
\right\},
\quad 0<\alpha<\beta<1,\\
t_i&\sim\nu_i(\mathcal B_i),\\
d_i
&=
\left(
x_{i,t_i},\
s_{i,t_i},\
U_{i,>t_i},\
\mathcal J_{i,t_i}
\right).
\end{aligned}
}
$$

$N_i$ 是预采集完整轨迹的长度，$\mathcal B_i^{\mathrm{legal}}$ 是工具交互已经完整结束的边界，$\alpha,\beta$ 预先设定为覆盖中段与后半程的区间，$r_i(t)$ 是剩余实质操作数量，$r_{\min}>0$ 用于排除任务已完成或只剩结束回复的位置。  
按阶段分层采样断点并重放前缀获得 $s_{i,t_i}$，各方法从同一状态、同一可见历史继续执行；同一原始任务可以产生多个独立重放的样本，但**每个样本只压缩一次**。  
完整轨迹长度、未来请求和 GT 仅用于离线构造及评分，不进入压缩器；所有同源断点和增强任务放在同一数据划分中。

## 14. 训练方法设计

### 算法：任务监督的图删改学习

### 1）构造候选图与离线搜索空间

使用固定抽取器 $P$ 生成 $G^0$，保留对象、状态、结果、约束及其证据关系，然后从当前图 $G_j$ 生成合法删改：

$$
G'=a(G_j),
\qquad
a\in\mathcal A_{\mathrm{legal}}(G_j),
\qquad
\Delta L=L(G_j)-L(G').
$$

搜索先尝试较大的冗余块，再尝试事实和字段；未经优化的 $G^0$ 也必须与完整历史比较，以区分抽取错误和删减错误，且抽取引起的失败仍计入最终端到端评价。

这一“测试后删减、保留目标行为”的搜索思路参考 Delta Debugging，但不将其局部简化性质直接当成全局最小图保证。参见文献 [3]。

### 2）通过后续任务回放生成监督

对每个候选图 $G'$，从相同断点状态继续执行，并与完整历史参考进行配对比较；进行 $K$ 次运行时，经验破坏率定义为：

$$
\boxed{
\widehat y_{i,t}(G')
=
\frac{
\sum_{k=1}^{K}
Y_{i,t}(H_{i,\le t};\omega_k)
\left[1-Y_{i,t}(S(G');\omega_k)\right]
}{
\sum_{k=1}^{K}
Y_{i,t}(H_{i,\le t};\omega_k)
}
}
$$

它衡量“完整历史能够成功的运行中，候选记忆导致失败的比例”；分母为零时不生成安全性标签，不能将“两者都失败”标为安全。

保存成功和失败的删改记录，继续搜索更短且通过预设训练验收的候选；**每个候选始终与原始完整历史比较，而不是只与上一次压缩结果比较**。

### 3）训练轻量删改风险模型

第一版训练一个**两层隐藏层的 MLP 风险模型**，可从每层 128 个单元起步；不训练基础 LLM，也不要求使用 GNN。

$$
\boxed{
\begin{aligned}
p_\theta(a\mid G^0,G)
&=
\sigma\!\left(
\operatorname{MLP}_\theta
\bigl(\Phi(G^0,G,a)\bigr)
\right),\\
\mathcal L(\theta)
&=
-\sum_{n}w_n
\left[
\widehat y_n\log p_{\theta,n}
+
(1-\widehat y_n)\log(1-p_{\theta,n})
\right].
\end{aligned}
}
$$

$\Phi$ 包含 token 节省量、剩余替代事实、对象与版本依赖、当前已知目标匹配、信息时效性和累计删减等特征；$w_n$ 按原始任务平衡，避免拥有大量候选动作的任务主导训练。

模型预测的是**当前删改后的累计任务破坏风险**，而非一个节点永久不变的重要性；训练标签可以使用未来任务结果，但模型特征不能包含未来请求或 GT。

### 4）风险约束下选择删改，并校准部署策略

实际压缩时，不再回放未来任务，而是在预测风险不超过阈值的动作中选择节省最多的动作：

$$
\boxed{
a_j^*
\in
\arg\max_{a\in\mathcal A_{\mathrm{legal}}(G_j)}
\left[L(G_j)-L(a(G_j))\right]
\quad
\text{s.t.}\quad
p_\theta(a\mid G^0,G_j)\le\rho,
\qquad
G_{j+1}=a_j^*(G_j).
}
$$

每次编辑后重新生成候选和评分，没有合格动作或达到计算预算时停止；$\rho$ 在开发集上根据完整压缩流程的性能—成本曲线确定，再锁定用于测试。

**一次压缩可以包含多次图编辑，但不等于一个任务被反复压缩。** 风险预测只是选择依据，不构成性能保持或全局最小性的证明。

## 15. 如何 Evaluate

在留出 BFCL 任务族上，对第 12 节列出的主要比较方法、完整历史、强文本压缩、未优化图、固定规则删减、无图事实选择器和本方法进行同断点配对评估，并分别报告中段与后半程结果。  
固定规则删减与本方法共享候选图和合法操作；无图对照匹配可见事实、关系及限定信息、任务监督和训练／推理预算，但不使用显式图拓扑进行编辑选择。报告各方法的操作空间差异，以区分学习机制、结构约束与信息或预算差异带来的收益。  
开发集确定阈值后锁定方法，在 AppWorld 上验证，并按任务族构造成功率差和成本差的置信区间：

$$
\boxed{
\begin{aligned}
\operatorname{LCB}_{1-\delta}
\left(
\widehat{\operatorname{Succ}}_\theta
-
\widehat{\operatorname{Succ}}_{\mathrm{full}}
\right)
&\ge-\varepsilon,\\
\operatorname{UCB}_{1-\delta}
\left(
\overline C_\theta-\overline C_{\mathrm{text}}
\right)
&<0,\\
C_m
&=
C_m^{\mathrm{构图与压缩}}
+
C_m^{\mathrm{后续LLM}}
+
C_m^{\mathrm{后续工具}}.
\end{aligned}
}
$$

LCB/UCB 分别是置信下界和上界，成本 $C_m$ 使用预先选定的统一单位并计入正常缓存、额外查询和压缩开销，训练成本另行报告，且成本比较仅在双方均满足性能保持标准的配置间进行。

## 16. 相关文献

**[1] Patil, S. G., et al. (2025).** *The Berkeley Function Calling Leaderboard (BFCL): From Tool Use to Agentic Evaluation of Large Language Models.* **ICML 2025.**  
用途：主要任务数据及工具执行评价；多轮子集的具体构造同时参考官方 V3 文档。  
[论文页面][1] · [BFCL 官方多轮说明][bfcl-mt]

**[2] Trivedi, H., et al. (2024).** *AppWorld: A Controllable World of Apps and People for Benchmarking Interactive Coding Agents.* **ACL 2024.**  
用途：多应用环境中的外部验证，以及基于状态的程序化验收。  
[论文页面][2] · [官方仓库][appworld-repo]

**[3] Zeller, A., & Hildebrandt, R. (2002).** *Simplifying and Isolating Failure-Inducing Input.* **IEEE Transactions on Software Engineering.**  
用途：通过反复测试进行输入删减的算法基础；帮助区分局部不可再删与全局最小。  
[论文页面][3]

**[4] Weiser, M. (1984).** *Program Slicing.* **IEEE Transactions on Software Engineering.**  
用途：基于数据流和控制流依赖筛选信息的理论来源；我们的未知后续任务设置不同于具有明确切片准则的经典程序切片。  
[论文页面][4]

**[5] Pan, Z., et al. (2024).** *LLMLingua-2: Data Distillation for Efficient and Faithful Task-Agnostic Prompt Compression.* **Findings of ACL 2024.**  
用途：将压缩转化为分类、用蒸馏训练较小模型的参考，也是非图文本压缩基线。  
[论文页面][5]

**[6] Kang, M., et al. (2026).** *ACON: Optimizing Context Compression for Long-horizon LLM Agents.* **ICML 2026.**  
用途：最直接的相关方法与强基线，使用完整上下文成功、压缩上下文失败的反馈改进压缩，并将压缩器蒸馏到小模型；因此，本研究的差异应在**图删改语义与风险引导选择**，而不是任务反馈本身。  
[论文页面][6] · [本稿对比版本：arXiv v3][acon-version]

**[7] Fatemi, B., Halcrow, J., & Perozzi, B. (2024).** *Talk like a Graph: Encoding Graphs for Large Language Models.* **ICLR 2024.**  
用途：显式图通过文本交给固定 LLM 的接口依据，以及控制图编码方式影响的实验参考。  
[论文页面][7]

**[8] Guan, X., Zhao, Q., & Deng, Y. (2026).** *Decision-Aware Memory Cards: Counterfactual-Inspired Context Selection and Compression for Tool-Using LLM Agents.* **arXiv:2606.08151，预印本。**  
用途：上下文相关效用、图辅助选择和轻量排序的相关方法；与本研究的差异在于以完整历史为参照、由续段回放监督的整图删改风险目标，而不是泛指“决策感知”。  
[论文页面][8]

**[9] Wu, Y., et al. (2026).** *ContextWeaver: Selective and Dependency-Structured Memory Construction for LLM Agents.* **arXiv:2604.23069v1，预印本。**  
用途：步骤依赖图、祖先选择、依赖摘要与执行验证的相关方法；用于区分步骤级历史组织与任务监督的状态级图编辑。  
[论文页面][9]

**[10] Tan, X., et al. (2026).** *SkillZip: Contract-Preserving Graph Compression for Scalable Agent Skill Libraries.* **arXiv:2608.05604v1，预印本。**  
用途：契约保持的可逆技能宏压缩与按需展开；用于区分可复用过程抽象与允许丢弃历史细节的任务内工作记忆压缩。  
[论文页面][10]

---

[1]: https://proceedings.mlr.press/v267/patil25a.html
[2]: https://aclanthology.org/2024.acl-long.850/
[3]: https://www.st.cs.uni-saarland.de/papers/tse2002/
[4]: https://ieeexplore.ieee.org/document/5010248
[5]: https://aclanthology.org/2024.findings-acl.57/
[6]: https://www.microsoft.com/en-us/research/publication/acon-optimizing-context-compression-for-long-horizon-llm-agents/
[7]: https://proceedings.iclr.cc/paper_files/paper/2024/hash/bf72f65f30eedf5d48da6980ee02b589-Abstract-Conference.html
[8]: https://arxiv.org/html/2606.08151v2
[bfcl-mt]: https://gorilla.cs.berkeley.edu/blogs/13_bfcl_v3_multi_turn.html
[appworld-repo]: https://github.com/StonyBrookNLP/appworld

[9]: https://arxiv.org/html/2604.23069v1
[10]: https://arxiv.org/html/2608.05604v1
[acon-version]: https://arxiv.org/html/2510.00615v3
