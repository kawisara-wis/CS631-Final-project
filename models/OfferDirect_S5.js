const mongoose = require('mongoose');
const mongooseHistory = require('mongoose-history');
const config = require("../config.json");

const offerDirectSchema = new mongoose.Schema({
  seller: { type: mongoose.Schema.Types.ObjectId, ref: 'Account', required: true },
  buyer: { type: mongoose.Schema.Types.ObjectId, ref: 'Account', required: true },
  price: { type: Number, required: true },
  expiryTimestamp: { type: Number },
  state: { type: String, enum: ['IDLE', 'MARKET', 'EXPIRED', 'ACCEPTED', 'REJECTED'], default: 'IDLE' },
  service: { type: mongoose.Schema.Types.ObjectId, ref: 'Service', required: true },
  createdAt: { type: Date, default: Date.now },
  updatedAt: { type: Date, default: Date.now },
  scenario: { type: Number, default: 5 }
}, { collection: 'offerdirects_S5' });

offerDirectSchema.plugin(mongooseHistory);

module.exports = mongoose.model('OfferDirect_S5', offerDirectSchema);