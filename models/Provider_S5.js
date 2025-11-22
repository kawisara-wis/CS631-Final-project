const mongoose = require("mongoose");
const mongooseHistory = require("mongoose-history");
const config = require("../config.json");

const providerSchema = new mongoose.Schema( {
    //Account id
    account: {type: mongoose.Schema.Types.ObjectId, ref: 'Account', required: true},
    
    // --- ✅ (เพิ่มบรรทัดนี้) ---
    agentType: {type: String, default: 'random'},
    // --- ✅ ---

    //List of services
    services: [{type: mongoose.Schema.Types.ObjectId, ref: 'Service'}],
    //Number of services provider can process at the same time
    servicesLimit: {type: Number, default: 5},
    // (Location data)
    location: {
        x: {type: Number, default: 0},
        y: {type: Number, default: 0}
    },
    // (Timestamps)
    createdAt: {type: Date, default: Date.now},
    updatedAt: {type: Date, default: Date.now}
},
{
    collection: 'provider_s5' 
}
);

providerSchema.plugin(mongooseHistory)

module.exports = mongoose.model('Provider_S5', providerSchema);

providerSchema.pre('save', function (next) {
    if (this.isNew) {
        this.createdAt = new Date(); // Or your custom timestamp
    } else {
        this.updatedAt = new Date(); // Or your custom timestamp
    }
    next();
});

providerSchema.plugin(mongooseHistory)

module.exports = mongoose.model('Provider_S5', providerSchema);