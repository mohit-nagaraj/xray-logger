"""Sample competitor document data for the RAG pipeline example.

This module provides a simulated corpus of documents about competitors
and market analysis. Each document has relevance scores that will be
used for filtering and ranking in the pipeline.
"""

DOCUMENTS = [
    {
        "id": "DOC001",
        "title": "Competitor A Launches AI-Powered Analytics Platform",
        "content": "Competitor A announced today the launch of their new AI-powered analytics platform. The system uses machine learning to provide real-time insights into customer behavior and market trends. Early adopters report a 40% improvement in decision-making speed.",
        "source": "press_release",
        "date": "2024-01-15",
        "relevance_score": 0.92,
    },
    {
        "id": "DOC002",
        "title": "Market Analysis: Observability Tools Growth Report",
        "content": "Industry analysts report that the observability and monitoring market is projected to grow 15% annually through 2027. Key drivers include cloud adoption, microservices architectures, and the need for real-time system visibility.",
        "source": "analyst_report",
        "date": "2024-01-12",
        "relevance_score": 0.85,
    },
    {
        "id": "DOC003",
        "title": "Competitor B Raises $50M Series C",
        "content": "Competitor B has raised $50 million in Series C funding to expand their machine learning infrastructure. The company plans to use the funds to hire 100 engineers and expand into the European market.",
        "source": "news_article",
        "date": "2024-01-10",
        "relevance_score": 0.78,
    },
    {
        "id": "DOC004",
        "title": "Technical Deep Dive: Modern Pipeline Architectures",
        "content": "This technical white paper explores modern data pipeline architectures. Topics include event-driven systems, real-time processing, and observability patterns for complex ML workflows.",
        "source": "white_paper",
        "date": "2024-01-08",
        "relevance_score": 0.88,
    },
    {
        "id": "DOC005",
        "title": "Competitor C Product Comparison Review",
        "content": "An independent review comparing Competitor C's analytics suite against alternatives. Key findings: strong visualization capabilities but limited real-time processing support.",
        "source": "review",
        "date": "2024-01-05",
        "relevance_score": 0.72,
    },
    {
        "id": "DOC006",
        "title": "Industry Trends: AI Integration in DevOps",
        "content": "AI is transforming DevOps practices. Companies are increasingly using AI for automated testing, intelligent monitoring, and predictive maintenance. Early adopters see 30% reduction in incident response times.",
        "source": "industry_report",
        "date": "2024-01-14",
        "relevance_score": 0.81,
    },
    {
        "id": "DOC007",
        "title": "Competitor A Partnership Announcement",
        "content": "Competitor A announced a strategic partnership with a major cloud provider. The partnership will enable deeper integration with cloud-native services and expanded global reach.",
        "source": "press_release",
        "date": "2024-01-03",
        "relevance_score": 0.65,
    },
    {
        "id": "DOC008",
        "title": "Customer Success Story: Enterprise ML Platform",
        "content": "A Fortune 500 company shares their experience implementing an enterprise ML platform. Key learnings include the importance of observability, decision tracking, and reproducibility.",
        "source": "case_study",
        "date": "2024-01-11",
        "relevance_score": 0.89,
    },
    {
        "id": "DOC009",
        "title": "Regulatory Changes Impacting AI Systems",
        "content": "New regulations require AI systems to provide explainability and audit trails. Companies must now document decision-making processes and maintain logs for compliance.",
        "source": "regulatory_update",
        "date": "2024-01-09",
        "relevance_score": 0.74,
    },
    {
        "id": "DOC010",
        "title": "Outdated: 2022 Market Overview",
        "content": "This older report from 2022 provides historical context on the observability market. While dated, it offers baseline metrics for year-over-year comparison.",
        "source": "analyst_report",
        "date": "2022-06-15",
        "relevance_score": 0.45,
    },
]
