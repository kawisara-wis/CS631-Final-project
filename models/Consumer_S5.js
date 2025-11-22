const {mongoose} = require('mongoose');
const  mongooseHistory = require('mongoose-history');

const consumerSchema=new mongoose.Schema( {
    //Cross-reference to Account schema
    account: {type: mongoose.Schema.Types.ObjectId, ref: 'Account'},
    //Cross-reference to Service schema
    services: [{type: mongoose.Schema.Types.ObjectId, ref: 'Service'}],

    // --- เพิ่ม 3 บรรทัดนี้ ---
    location: { // 📍 ที่ตั้งของ Consumer (ลูกค้า/พัสดุ)
        x: Number,
        y: Number
    },
    // --- สิ้นสุด ---
    
    createdAt: {type: Date, default: Date.now},
    updatedAt: {type: Date, default: Date.now}
    },
);

consumerSchema.pre('save', function (next) {
    if (this.isNew) {
        this.createdAt = new Date(); // Or your custom timestamp
    } else {
        this.updatedAt = new Date(); // Or your custom timestamp
    }
    next();
});

consumerSchema.plugin(mongooseHistory)

module.exports = mongoose.model('Consumer_S5', consumerSchema);


