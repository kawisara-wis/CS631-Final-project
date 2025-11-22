
const mongoose = require("mongoose");
const  mongooseHistory = require('mongoose-history');

let poolCapacity = new mongoose.Schema({
    offers: [{type: mongoose.Schema.Types.ObjectId, ref: 'OfferCapacity'}],
    providers: [{type: mongoose.Schema.Types.ObjectId, ref: 'Provider'}],
        createdAt: {type: Date, default: Date.now},
        updatedAt: {type: Date, default: Date.now}
    },
);

poolCapacity.pre('save', function (next) {
    if (this.isNew) {
        this.createdAt = new Date(); // Or your custom timestamp
    } else {
        this.updatedAt = new Date(); // Or your custom timestamp
    }
    next();
});

poolCapacity.plugin(mongooseHistory)

module.exports = mongoose.model('PoolCapacity', poolCapacity);

