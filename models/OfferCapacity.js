const mongoose = require("mongoose");
const  mongooseHistory = require('mongoose-history');

const offerCapacitySchema = new mongoose.Schema({
    seller: {type: mongoose.Schema.Types.ObjectId, ref: 'Account', required: true},
    buyer: {type: mongoose.Schema.Types.ObjectId, ref: 'Account'},
    //Cross-reference to Offer schema
    offerDirect: {type: mongoose.Schema.Types.ObjectId, ref: 'OfferDirect', required: true},
    price: {type: Number, required: true},
    fee: {type: Number, default: 0},
    expiryTimestamp: {type: Number, required: true},
    //states ["IDLE", "MARKET", "EXPIRED", "ACCEPTED", "REMOVED"]
    state: {type: String, default: "IDLE"},
    createdAt: {type: Date, default: Date.now},
    updatedAt: {type: Date, default: Date.now}
    },
);

offerCapacitySchema.pre('save', function (next) {
    if (this.isNew) {
        this.createdAt = new Date(); // Or your custom timestamp
    } else {
        this.updatedAt = new Date(); // Or your custom timestamp
    }
    next();
});

offerCapacitySchema.plugin(mongooseHistory)

module.exports = mongoose.model('OfferCapacity', offerCapacitySchema);