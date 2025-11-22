const mongoose = require("mongoose");
const  mongooseHistory = require('mongoose-history');

const serviceSchema = new mongoose.Schema( {
    //States ["IDLE", "MARKET","ACTIVE", "DONE"]
    state: {type: String, default: "IDLE"},
    //Cross-reference to Offer schema
    offers: [{type: mongoose.Schema.Types.ObjectId, ref: 'OfferDirect'}],
    //Start service timestamp
    startTimestamp: {type: Number},
    //End service timestamp
    endTimestamp: {type: Number},
    //Duration in seconds default to 1 hour
    duration: {type: Number, default: 3600},
    //Service consumer id
    consumer: {type: mongoose.Schema.Types.ObjectId, ref: 'Consumer', required: true},
    //Service provider id
    provider: {type: mongoose.Schema.Types.ObjectId, ref: 'Provider'},
    //Count
    count: {type: Number, default: 0},
        createdAt: {type: Date, default: Date.now},
        updatedAt: {type: Date, default: Date.now}
    },
);

serviceSchema.pre('save', function (next) {
    if (this.isNew) {
        this.createdAt = new Date(); // Or your custom timestamp
    } else {
        this.updatedAt = new Date(); // Or your custom timestamp
    }
    next();
});

serviceSchema.plugin(mongooseHistory)

module.exports = mongoose.model('Service', serviceSchema);
