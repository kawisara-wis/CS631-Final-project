const {mongoose} = require('mongoose');
const  mongooseHistory = require('mongoose-history');

const accountSchema = new mongoose.Schema({
    balance: {type: Number, default: 100},
    createdAt: {type: Date, default: Date.now},
    updatedAt: {type: Date, default: Date.now}
    },
);

accountSchema.pre('save', function (next) {
    if (this.isNew) {
        this.createdAt = new Date(); // Or your custom timestamp
    } else {
        this.updatedAt = new Date(); // Or your custom timestamp
    }
    next();
});

accountSchema.plugin(mongooseHistory)

module.exports = mongoose.model('Account', accountSchema);