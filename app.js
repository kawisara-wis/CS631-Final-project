const config = require('./config.json');

const {mongoose} = require('mongoose');

const FakeTimers = require("@sinonjs/fake-timers");
const clock = FakeTimers.install();

const serviceAccount = require('./services/Account');
const serviceConsumer = require('./services/Consumer');
const serviceProvider = require('./services/Provider');
const serviceOfferDirect = require('./services/OfferDirect');
const serviceService = require('./services/Service');
const servicePoolCapacity = require('./services/PoolCapacity'); 

const {promises} = require('./utils/events')
mongoose.connect(config.db.url).then(async () => {
    //Drop account collection
    try {
        //Drop account collection
        await serviceAccount.Account.deleteMany({});
        await serviceConsumer.Consumer.deleteMany({});
        await serviceService.Service.deleteMany({});
        await serviceProvider.Provider.deleteMany({});
        await serviceOfferDirect.OfferDirect.deleteMany({});
        await servicePoolCapacity.PoolCapacity.deleteMany({}); 

        // --- NEW LOGIC (แก้ไขตรงนี้) ---
        // 1. สร้าง Pool (ตลาด)
        let pool = await servicePoolCapacity.create();
        console.log("PoolCapacity created: " + pool.id);

        // 2. สร้าง Provider (พ่อค้า)
        let provider = await serviceProvider.create(await serviceAccount.create());
        console.log("Provider created: " + provider.id);

        // 3. ลงทะเบียน Provider เข้า Pool (นี่คือขั้นตอนที่ขาดไป)
        await servicePoolCapacity.addProvider(pool, provider);
        console.log("Provider added to Pool");

        // 4. สร้าง Consumer (ลูกค้า)
        let consumer = await serviceConsumer.create(await serviceAccount.create());
        console.log("Consumer created: " + consumer.id);
        // --- END NEW LOGIC ---


        await serviceConsumer.rentService(consumer);
        //
        for (let i = 0; i < 18000; i++) {
            await clock.tickAsync(1);
            //Flush all promises in queue
            await Promise.all(promises);

        }
    } catch (e) {
        console.log(e);
    }

        // clock.tickAsync(3000);
});


//
// clock.tick(5000);
// clock.runAllAsync();
// clock.tick(1000);
// clock.tick(1000);
// clock.tick(1000);
// clock.tick(1000);
//
// clock.tick(1000);
// clock.tick(1000);
// clock.tick(1000);
// clock.tick(1000);
// clock.tick(1000);
//
// clock.tick(1000);
// clock.tick(1000);
// clock.tick(1000);
// clock.tick(1000);
// clock.tick(1000);