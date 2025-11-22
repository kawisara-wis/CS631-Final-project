// runScenario3.js (Scenario 3: 1 Slot, With Pool)

// --- GLOBAL ERROR HANDLER ---
process.on('unhandledRejection', (reason, promise) => {
    const ignoreErrors = [
        "Last offer direct is in state MARKET",
        "Last service is in state ACTIVE",
        "Service not in state MARKET",
        "Offer not in state MARKET",
        "Account not defined",
        "Fee cannot be negative" // Scenario นี้อาจมีเรื่อง Fee เข้ามาเกี่ยวข้อง
    ];
    if (ignoreErrors.includes(reason)) return;
    // console.error('Unhandled Rejection:', reason);
});

const mongoose = require('mongoose');
const config = require('./config.json'); 
const logger = require('./utils/logger');

// Import Services
const serviceAccount = require('./services/Account');
const serviceProvider = require('./services/Provider');
const serviceConsumer = require('./services/Consumer');
const serviceService = require('./services/Service');
const servicePoolCapacity = require('./services/PoolCapacity'); // <--- เพิ่ม Pool Service
const Account = require('./models/Account');
const Provider = require('./models/Provider');
const Service = require('./models/Service');
const OfferDirect = require('./models/OfferDirect');

// --- SCENARIO 3 CONFIGURATION ---
const NUM_RANDOM_AGENTS = 4;
const NUM_AI_AGENTS = 1;
const SLOTS_PER_AGENT = 1; // <--- เปลี่ยนจาก 5 เป็น 1 (ตามงานวิจัย)
const NUM_CONSUMERS = 5;   // <--- เปลี่ยนจาก 25 เป็น 5 (Low Demand)
const SIMULATION_DURATION_MS = 60000;
const TRAFFIC_INTERVAL_MS = 1000; // ลดความถี่ลงนิดหน่อยเพราะคนน้อย

let agentStatsHistory = {};

// Seed History (AI ยังคงต้องเรียนรู้ราคาตลาด)
async function seedAIHistory(providerId, accountId) {
    logger.info(`[SEEDING] Creating history for AI Agent: ${providerId}`);
    // ราคากลางๆ เพื่อให้ AI พอรู้เรตราคา
    const historyPrices = [5, 8, 4, 9, 6, 10, 3, 7, 5, 8]; 

    for (let price of historyPrices) {
        let mockService = new Service({
            consumer: accountId, provider: providerId, state: "DONE", duration: 1000, count: 0
        });
        await mockService.save();
        let mockOffer = new OfferDirect({
            seller: accountId, buyer: accountId, service: mockService._id, price: price, state: "ACCEPTED", expiryTimestamp: Date.now() - 10000 
        });
        await mockOffer.save();
    }
}

async function initScenario() {
    try {
        await mongoose.connect(config.db.url, { useNewUrlParser: true, useUnifiedTopology: true });
        logger.info("Connected to MongoDB for Scenario 3...");

        // Clear Data
        await Account.deleteMany({});
        await Provider.deleteMany({});
        await require('./models/Consumer').deleteMany({});
        await Service.deleteMany({});
        await OfferDirect.deleteMany({});
        await require('./models/OfferCapacity').deleteMany({});
        await require('./models/PoolCapacity').deleteMany({});

        // 1. สร้าง Pool (ตลาดกลาง) *** สำคัญสำหรับ SC3 ***
        let pool = await servicePoolCapacity.create();
        logger.info(`Capacity Pool Created: ${pool._id}`);

        const agents = [];
        const consumers = [];

        // 2. Create Random Agents
        for (let i = 0; i < NUM_RANDOM_AGENTS; i++) {
            let acc = new Account({ balance: 1000 }); await acc.save();
            let provider = await serviceProvider.create(acc, { agentType: 'random' });
            provider.servicesLimit = SLOTS_PER_AGENT; 
            await provider.save();
            
            // Add to Pool
            await servicePoolCapacity.addProvider(pool, provider);
            
            agents.push({ id: provider._id, type: 'random', name: `Random_${i+1}` });
            agentStatsHistory[provider._id] = { 0:0, 1:0, totalSamples: 0 }; // เก็บแค่ 0 กับ 1 เพราะมีแค่ 1 Slot
        }

        // 3. Create AI Agent
        for (let i = 0; i < NUM_AI_AGENTS; i++) {
            let acc = new Account({ balance: 1000 }); await acc.save();
            let provider = await serviceProvider.create(acc, { agentType: 'ai' });
            provider.servicesLimit = SLOTS_PER_AGENT; 
            await provider.save();

            // Add to Pool
            await servicePoolCapacity.addProvider(pool, provider);

            agents.push({ id: provider._id, type: 'ai', name: `AI_Agent` });
            agentStatsHistory[provider._id] = { 0:0, 1:0, totalSamples: 0 };
            await seedAIHistory(provider._id, acc._id);
        }

        // 4. Create Consumers
        for (let i = 0; i < NUM_CONSUMERS; i++) {
            let acc = new Account({ balance: 5000 }); await acc.save();
            consumers.push(await serviceConsumer.create(acc));
        }

        logger.info("--- SIMULATION SCENARIO 3 RUNNING ---");
        
        let simulationTimer = setInterval(async () => {
            const randomConsumer = consumers[Math.floor(Math.random() * consumers.length)];
            serviceConsumer.rentService(randomConsumer).catch(() => {});

            // Sampling Data
            for (let agent of agents) {
                const activeCount = await Service.countDocuments({ provider: agent.id, state: 'ACTIVE' });
                if (agentStatsHistory[agent.id]) {
                    let safeCount = activeCount > 1 ? 1 : activeCount; // Max 1 Slot
                    agentStatsHistory[agent.id][safeCount]++;
                    agentStatsHistory[agent.id].totalSamples++;
                }
            }
        }, TRAFFIC_INTERVAL_MS);

        setTimeout(async () => {
            clearInterval(simulationTimer);
            await generateReport(agents);
            process.exit(0);
        }, SIMULATION_DURATION_MS);

    } catch (e) { console.error(e); process.exit(1); }
}

async function generateReport(agents) {
    console.log("\n=== SCENARIO 3 RESULT (1 Slot, With Pool) ===");
    console.log("Agent      | Empty(0) | Full(1)");
    console.log("-------------------------------");
    for (let agent of agents) {
        const stats = agentStatsHistory[agent.id];
        const total = stats.totalSamples || 1;
        const p0 = ((stats[0] / total) * 100).toFixed(1);
        const p1 = ((stats[1] / total) * 100).toFixed(1);
        console.log(`${agent.name.padEnd(10)} | ${p0.padStart(6)}%  | ${p1.padStart(6)}%`);
    }
}

initScenario();