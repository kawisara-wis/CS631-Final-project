const mongoose = require('mongoose');
const  mongooseHistory = require('mongoose-history');

const offerDirectSchema = new mongoose.Schema({
    seller: {type: mongoose.Schema.Types.ObjectId, ref: 'Account', required: true},
    buyer: {type: mongoose.Schema.Types.ObjectId, ref: 'Account'},
    price: {type: Number, required: true},
    expiryTimestamp: {type: Number},
    //states ["IDLE", "MARKET", "EXPIRED", "ACCEPTED", "REJECTED"]
    state: {type: String, default: "IDLE"},
    //Cross-reference to Service schema
    service: {type: mongoose.Schema.Types.ObjectId, ref: 'Service', required: true},
    //Creation timestamp
    createdAt: {type: Date, default: Date.now},
    //Update timestamp
    updatedAt: {type: Date, default: Date.now}
    },
);

offerDirectSchema.pre('save', function (next) {
    if (this.isNew) {
        this.createdAt = new Date(); // Or your custom timestamp
    } else {
        this.updatedAt = new Date(); // Or your custom timestamp
    }
    next();
});

offerDirectSchema.plugin(mongooseHistory)

module.exports = mongoose.model('OfferDirect', offerDirectSchema);
