const {mongoose} = require('mongoose');
const mongooseHistory = require('mongoose-history');
const config = require('../config.json'); // เราต้อง import config มาใช้

const providerSchema = new mongoose.Schema({
    //Cross-reference to Account schema
    account: {type: mongoose.Schema.Types.ObjectId, ref: 'Account', required: true},
    //Cross-reference to Service schema
    services: [{type: mongoose.Schema.Types.ObjectId, ref: 'Service'}],
    //Number of services a provider can handle at the same time
    servicesLimit: {type: Number, default: config.provider.servicesLimit},

    // --- เพิ่ม 2 บรรทัดนี้ ---
    // 'random' (สุ่ม) หรือ 'ai' (ใช้ LLM)
    agentType: {type: String, default: 'random'}, 
    // --- สิ้นสุด ---

    createdAt: {type: Date, default: Date.now},
    updatedAt: {type: Date, default: Date.now}
    },
);

providerSchema.pre('save', function (next) {
    if (this.isNew) {
        this.createdAt = new Date(); // Or your custom timestamp
    } else {
        this.updatedAt = new Date(); // Or your custom timestamp
    }
    next();
});

providerSchema.plugin(mongooseHistory)

module.exports = mongoose.model('Provider', providerSchema);