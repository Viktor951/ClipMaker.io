// Mock data simulating generated clips and word-level transcriptions
const MOCK_CLIPS = [
    {
        id: "clip-1",
        title: "O Segredo Que Ninguém Te Conta Sobre IA",
        duration: "00:42",
        durationSec: 42,
        viralScore: 98,
        hookReason: "Gancho com forte apelo de curiosidade nos primeiros 3 segundos. Alta taxa de retenção esperada para o TikTok.",
        thumbnail: "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=600&auto=format&fit=crop&q=80",
        words: [
            { id: "w1", text: "O", start: 0.1, end: 0.3, highlighted: false },
            { id: "w2", text: "maior", start: 0.4, end: 0.8, highlighted: false },
            { id: "w3", text: "segredo", start: 0.9, end: 1.4, highlighted: true },
            { id: "w4", text: "da", start: 1.5, end: 1.6, highlighted: false },
            { id: "w5", text: "inteligência", start: 1.7, end: 2.3, highlighted: false },
            { id: "w6", text: "artificial", start: 2.4, end: 3.1, highlighted: true },
            { id: "w7", text: "não", start: 3.2, end: 3.5, highlighted: false },
            { id: "w8", text: "é", start: 3.6, end: 3.8, highlighted: false },
            { id: "w9", text: "o", start: 3.9, end: 4.0, highlighted: false },
            { id: "w10", text: "código,", start: 4.1, end: 4.7, highlighted: false },
            { id: "w11", text: "mas", start: 4.8, end: 5.0, highlighted: false },
            { id: "w12", text: "sim", start: 5.1, end: 5.4, highlighted: false },
            { id: "w13", text: "o", start: 5.5, end: 5.6, highlighted: false },
            { id: "w14", text: "volume", start: 5.7, end: 6.2, highlighted: true },
            { id: "w15", text: "de", start: 6.3, end: 6.4, highlighted: false },
            { id: "w16", text: "dados", start: 6.5, end: 7.0, highlighted: false },
            { id: "w17", text: "qualificados.", start: 7.1, end: 8.0, highlighted: true }
        ]
    },
    {
        id: "clip-2",
        title: "Por Que Você Vai Perder Seu Trabalho?",
        duration: "00:55",
        durationSec: 55,
        viralScore: 94,
        hookReason: "Gatilho de urgência e medo focado em profissionais de tecnologia e criativos.",
        thumbnail: "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=600&auto=format&fit=crop&q=80",
        words: [
            { id: "w201", text: "Se", start: 0.1, end: 0.3, highlighted: false },
            { id: "w202", text: "você", start: 0.4, end: 0.6, highlighted: false },
            { id: "w203", text: "não", start: 0.7, end: 0.9, highlighted: false },
            { id: "w204", text: "aprender", start: 1.0, end: 1.5, highlighted: false },
            { id: "w205", text: "a", start: 1.6, end: 1.7, highlighted: false },
            { id: "w206", text: "automatizar", start: 1.8, end: 2.5, highlighted: true },
            { id: "w207", text: "suas", start: 2.6, end: 2.8, highlighted: false },
            { id: "w208", text: "tarefas", start: 2.9, end: 3.4, highlighted: false },
            { id: "w209", text: "hoje,", start: 3.5, end: 4.0, highlighted: true },
            { id: "w210", text: "alguém", start: 4.1, end: 4.5, highlighted: false },
            { id: "w211", text: "vai", start: 4.6, end: 4.8, highlighted: false },
            { id: "w212", text: "fazer", start: 4.9, end: 5.2, highlighted: false },
            { id: "w213", text: "isso", start: 5.3, end: 5.6, highlighted: false },
            { id: "w214", text: "por", start: 5.7, end: 5.9, highlighted: false },
            { id: "w215", text: "você.", start: 6.0, end: 6.6, highlighted: true }
        ]
    },
    {
        id: "clip-3",
        title: "A Regra dos 5 Minutos Para Produtividade",
        duration: "00:38",
        durationSec: 38,
        viralScore: 88,
        hookReason: "Técnica acionável imediatamente. Alto compartilhamento em comunidades de auto-aperfeiçoamento.",
        thumbnail: "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=600&auto=format&fit=crop&q=80",
        words: [
            { id: "w301", text: "Apenas", start: 0.1, end: 0.5, highlighted: false },
            { id: "w302", text: "comece", start: 0.6, end: 1.0, highlighted: true },
            { id: "w303", text: "por", start: 1.1, end: 1.3, highlighted: false },
            { id: "w304", text: "cinco", start: 1.4, end: 1.8, highlighted: true },
            { id: "w305", text: "minutos.", start: 1.9, end: 2.5, highlighted: true },
            { id: "w306", text: "O", start: 2.6, end: 2.7, highlighted: false },
            { id: "w307", text: "cérebro", start: 2.8, end: 3.3, highlighted: false },
            { id: "w308", text: "odeia", start: 3.4, end: 3.8, highlighted: false },
            { id: "w309", text: "deixar", start: 3.9, end: 4.2, highlighted: false },
            { id: "w310", text: "tarefas", start: 4.3, end: 4.8, highlighted: false },
            { id: "w311", text: "incompletas.", start: 4.9, end: 5.8, highlighted: true }
        ]
    }
];
