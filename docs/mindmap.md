# 医院红外热成像诊断系统 - 项目思维导图

```mermaid
graph LR
    Root[医院红外热成像诊断系统]
    
    Root --> Web[前端应用]
    Root --> Backend[后端服务]
    Root --> Core[核心功能模块]
    Root --> Flow[数据流转]
    Root --> Tech[技术栈]
    Root --> Deploy[部署运维]
    
    Web --> F1[患者登记页面]
    F1 --> F1_1[新增患者登记]
    F1 --> F1_2[患者列表查询]
    F1 --> F1_3[患者信息展示]
    F1 --> F1_4[病历查看]
    F1 --> F1_5[历史报告]
    
    Web --> F2[数据上传页面]
    F2 --> F2_1[文件上传]
    F2 --> F2_2[设备信息录入]
    F2 --> F2_3[患者信息关联]
    F2 --> F2_4[自动跳转诊断]
    
    Web --> F3[诊断分析页面]
    F3 --> F3_1[生成诊断报告]
    F3 --> F3_2[查询病历]
    F3 --> F3_3[导出JSON]
    F3 --> F3_4[导出PDF]
    F3 --> F3_5[打印报告]
    F3 --> F3_6[温度指标展示]
    F3 --> F3_7[历史报告查看]
    
    Web --> F4[治疗方案页面]
    F4 --> F4_1[患者病历选择]
    F4 --> F4_2[自动读取上下文]
    F4 --> F4_3[生成灸疗方案]
    F4 --> F4_4[穴位推荐]
    F4 --> F4_5[疗程参数设置]
    
    Web --> F5[疗效对比页面]
    F5 --> F5_1[治疗前后对比]
    F5 --> F5_2[温度变化分析]
    F5 --> F5_3[疗效评估]
    
    Web --> F6[状态管理]
    F6 --> F6_1[LocalStorage持久化]
    F6 --> F6_2[患者流程状态]
    F6 --> F6_3[页面数据保留]
    F6 --> F6_4[新增患者清空]
    
    Backend --> B1[数据接入]
    B1 --> B1_1[文件上传接口]
    B1 --> B1_2[元数据验证]
    B1 --> B1_3[质量检查QC]
    B1 --> B1_4[设备轮询]
    B1 --> B1_5[批量导入]
    
    Backend --> B2[数据分析]
    B2 --> B2_1[温度指标计算]
    B2 --> B2_2[区域对比分析]
    B2 --> B2_3[风险等级评估]
    B2 --> B2_4[热成像图生成]
    
    Backend --> B3[病历管理]
    B3 --> B3_1[EMR生成]
    B3 --> B3_2[EMR查询]
    B3 --> B3_3[EMR更新]
    B3 --> B3_4[归档管理]
    
    Backend --> B4[患者管理]
    B4 --> B4_1[患者注册]
    B4 --> B4_2[信息去重]
    B4 --> B4_3[患者列表]
    B4 --> B4_4[分页查询]
    
    Backend --> B5[报告管理]
    B5 --> B5_1[报告列表]
    B5 --> B5_2[按日期筛选]
    B5 --> B5_3[在线预览]
    B5 --> B5_4[文件下载]
    B5 --> B5_5[DOCX生成]
    
    Backend --> B6[数据平台]
    B6 --> B6_1[MySQL存储]
    B6 --> B6_2[患者表]
    B6 --> B6_3[记录表]
    B6 --> B6_4[病历表]
    B6 --> B6_5[报告表]
    
    Core --> C1[温度分析引擎]
    C1 --> C1_1[CSV数据加载]
    C1 --> C1_2[网格数据处理]
    C1 --> C1_3[统计指标计算]
    C1 --> C1_4[区域温度对比]
    C1 --> C1_5[异常区域识别]
    
    Core --> C2[诊断报告生成]
    C2 --> C2_1[AI诊断分析]
    C2 --> C2_2[风险等级评估]
    C2 --> C2_3[医生意见建议]
    C2 --> C2_4[治疗方案推荐]
    
    Core --> C3[热成像处理]
    C3 --> C3_1[图像生成]
    C3 --> C3_2[温度可视化]
    C3 --> C3_3[标注叠加]
    C3 --> C3_4[Matplotlib渲染]
    
    Core --> C4[文档生成]
    C4 --> C4_1[python-docx]
    C4 --> C4_2[报告模板]
    C4 --> C4_3[患者信息填充]
    C4 --> C4_4[温度指标展示]
    C4 --> C4_5[图片嵌入]
    
    Flow --> FL1[业务流程]
    FL1 --> FL1_1[患者登记]
    FL1_1 --> FL1_2[数据上传]
    FL1_2 --> FL1_3[诊断分析]
    FL1_3 --> FL1_4[治疗方案]
    FL1_4 --> FL1_5[疗效对比]
    
    Flow --> FL2[持久化策略]
    FL2 --> FL2_1[前端状态保存]
    FL2 --> FL2_2[后端数据库存储]
    FL2 --> FL2_3[文件系统归档]
    FL2 --> FL2_4[报告文档生成]
    
    Tech --> T1[前端技术]
    T1 --> T1_1[Next.js 15]
    T1 --> T1_2[React 19]
    T1 --> T1_3[TypeScript]
    T1 --> T1_4[TailwindCSS]
    T1 --> T1_5[Mammoth.js]
    
    Tech --> T2[后端技术]
    T2 --> T2_1[Python 3.12]
    T2 --> T2_2[FastAPI]
    T2 --> T2_3[PyMySQL]
    T2 --> T2_4[NumPy]
    T2 --> T2_5[Matplotlib]
    T2 --> T2_6[python-docx]
    
    Tech --> T3[数据存储]
    T3 --> T3_1[MySQL数据库]
    T3 --> T3_2[本地文件系统]
    T3 --> T3_3[JSON元数据]
    T3 --> T3_4[DOCX报告]
    
    Deploy --> D1[开发环境]
    D1 --> D1_1[make install]
    D1 --> D1_2[make run]
    D1 --> D1_3[热重载]
    
    Deploy --> D2[数据目录]
    D2 --> D2_1[data记录数据]
    D2 --> D2_2[reports报告文档]
    D2 --> D2_3[device-drop设备采集]
    D2 --> D2_4[device-processed已处理]
    
    Deploy --> D3[API服务]
    D3 --> D3_1[localhost:8000]
    D3 --> D3_2[CORS跨域支持]
    D3 --> D3_3[文件服务]
    
    Deploy --> D4[前端服务]
    D4 --> D4_1[localhost:3000]
    D4 --> D4_2[SSR渲染]
    D4 --> D4_3[客户端交互]
    
    style Root fill:#e74c3c,stroke:#fff,stroke-width:4px,color:#fff
    style Web fill:#3498db,stroke:#fff,stroke-width:2px,color:#fff
    style Backend fill:#f39c12,stroke:#fff,stroke-width:2px,color:#fff
    style Core fill:#9b59b6,stroke:#fff,stroke-width:2px,color:#fff
    style Flow fill:#27ae60,stroke:#fff,stroke-width:2px,color:#fff
    style Tech fill:#e67e22,stroke:#fff,stroke-width:2px,color:#fff
    style Deploy fill:#5dade2,stroke:#fff,stroke-width:2px,color:#fff
    
    classDef defaultStyle fill:#2980b9,stroke:#3498db,stroke-width:2px,color:#fff,font-weight:bold
    class F1,F2,F3,F4,F5,F6,B1,B2,B3,B4,B5,B6,C1,C2,C3,C4,FL1,FL2,T1,T2,T3,D1,D2,D3,D4 defaultStyle
    
    classDef leafStyle fill:#16a085,stroke:#1abc9c,stroke-width:2px,color:#fff,font-weight:bold
    class F1_1,F1_2,F1_3,F1_4,F1_5,F2_1,F2_2,F2_3,F2_4,F3_1,F3_2,F3_3,F3_4,F3_5,F3_6,F3_7,F4_1,F4_2,F4_3,F4_4,F4_5,F5_1,F5_2,F5_3,F6_1,F6_2,F6_3,F6_4 leafStyle
    class B1_1,B1_2,B1_3,B1_4,B1_5,B2_1,B2_2,B2_3,B2_4,B3_1,B3_2,B3_3,B3_4,B4_1,B4_2,B4_3,B4_4,B5_1,B5_2,B5_3,B5_4,B5_5,B6_1,B6_2,B6_3,B6_4,B6_5 leafStyle
    class C1_1,C1_2,C1_3,C1_4,C1_5,C2_1,C2_2,C2_3,C2_4,C3_1,C3_2,C3_3,C3_4,C4_1,C4_2,C4_3,C4_4,C4_5 leafStyle
    class FL1_1,FL1_2,FL1_3,FL1_4,FL1_5,FL2_1,FL2_2,FL2_3,FL2_4 leafStyle
    class T1_1,T1_2,T1_3,T1_4,T1_5,T2_1,T2_2,T2_3,T2_4,T2_5,T2_6,T3_1,T3_2,T3_3,T3_4 leafStyle
    class D1_1,D1_2,D1_3,D2_1,D2_2,D2_3,D2_4,D3_1,D3_2,D3_3,D4_1,D4_2,D4_3 leafStyle
```

## 系统架构概览

### 1. 前端应用层
- **患者登记系统**：患者信息管理、去重、历史查询
- **数据采集流程**：上传设备数据、关联患者、自动分析
- **诊断分析中心**：报告生成、温度分析、风险评估
- **治疗方案管理**：基于诊断的智能治疗建议
- **疗效追踪对比**：治疗前后数据对比分析

### 2. 后端服务层
- **设备数据接入**：文件上传、设备轮询、批量导入
- **智能分析引擎**：温度计算、区域对比、风险评估
- **病历管理系统**：EMR生成、查询、更新、归档
- **报告生成服务**：DOCX文档、在线预览、打印下载

### 3. 数据存储层
- **MySQL数据库**：患者、记录、病历、报告
- **文件系统**：原始数据、热成像图、报告文档
- **状态持久化**：LocalStorage、JSON配置

### 4. 核心算法
- **温度分析**：统计计算、区域对比、异常检测
- **图像处理**：热力图生成、温度可视化
- **诊断推理**：风险分级、治疗建议

### 5. 业务流程
```
患者登记 → 数据上传 → 诊断分析 → 生成报告 → 治疗方案 → 疗效评估
   ↓         ↓          ↓          ↓         ↓         ↓
 数据库    文件存储   分析引擎   报告文档   穴位推荐   对比分析
```

### 6. 特色功能
- **状态保持**：跨页面数据保留，仅新增患者时清空
- **智能预填**：诊断分析后自动带入治疗方案
- **多格式导出**：JSON、PDF、DOCX、打印预览
- **历史追溯**：患者报告文件管理、在线查看
- **去重机制**：姓名+性别+年龄签名避免重复

## 技术亮点

1. **全栈TypeScript**：类型安全、开发效率高
2. **微服务架构**：前后端分离、独立部署
3. **智能分析**：温度网格处理、区域异常检测
4. **文档自动化**：基于模板的报告批量生成
5. **用户体验**：状态持久化、无感数据恢复
6. **中医特色**：艾灸穴位推荐、疗程方案定制
