const config = require('../config.json');

const {mongoose} = require('mongoose');
const serviceConsumer = require("../services/Consumer");
const serviceService = require("../services/Service");
const serviceOfferDirect = require("../services/OfferDirect");


mongoose.connect(config.db.url).then(async () => {
    //Analyse consumers
    let consumers = await serviceConsumer.Consumer.find({});
    //Sort by _id
    consumers.sort((a, b) => {
        return a._id - b._id;
    });
    //Write to console in blue number of consumers
    console.log("\x1b[34m", "CONSUMERS");
    console.log("\x1b[34m", "Number of consumers: " + consumers.length);

    //Calculate average number of services per consumer
       let totalServices = 0;
    for (let consumer of consumers) {
        let services = await serviceService.Service.find({seller: consumer.account});
        totalServices += services.length;
    }
    let averageServices = totalServices / consumers.length;
    console.log("\x1b[34m", "Average number of services per consumer: " + averageServices);

    //Calculate average number of direct offers per consumer
    let totalDirectOffers = 0;
    for (let consumer of consumers) {
        let offers = await serviceOfferDirect.OfferDirect.find({seller: consumer.account});
        totalDirectOffers += offers.length;
    }
    let averageDirectOffers = totalDirectOffers / consumers.length;
    console.log("\x1b[34m", "Average number of direct offers per consumer: " + averageDirectOffers);

    //Calculate average number of direct offers that were accepted per consumer
    let totalDirectOffersAccepted = 0;
    for (let consumer of consumers) {
        let offers = await serviceOfferDirect.OfferDirect.find({seller: consumer.account, state: "ACCEPTED"});
        totalDirectOffersAccepted += offers.length;
    }
    let averageDirectOffersAccepted = totalDirectOffersAccepted / consumers.length;
    console.log("\x1b[34m", "Average number of direct offers accepted per consumer: " + averageDirectOffersAccepted);

    //Calculate average number of direct offers that were rejected per consumer
    let totalDirectOffersRejected = 0;
    for (let consumer of consumers) {
        let offers = await serviceOfferDirect.OfferDirect.find({seller: consumer.account, state: "REJECTED"});
        totalDirectOffersRejected += offers.length;
    }
    let averageDirectOffersRejected = totalDirectOffersRejected / consumers.length;
    console.log("\x1b[34m", "Average number of direct offers rejected per consumer: " + averageDirectOffersRejected);

    //Calculate average number of direct offers that expired per consumer
    let totalDirectOffersExpired = 0;
    for (let consumer of consumers) {
        let offers = await serviceOfferDirect.OfferDirect.find({seller: consumer.account, state: "EXPIRED"});
        totalDirectOffersExpired += offers.length;
    }
    let averageDirectOffersExpired = totalDirectOffersExpired / consumers.length;
    console.log("\x1b[34m", "Average number of direct offers expired per consumer: " + averageDirectOffersExpired);

    //Calculate average price of direct offers
    let totalDirectOffersPrice = 0;
    for (let consumer of consumers) {
        let offers = await serviceOfferDirect.OfferDirect.find({seller: consumer.account});
        for (let offer of offers) {
            totalDirectOffersPrice += offer.price;
        }
    }
    let averageDirectOffersPrice = totalDirectOffersPrice / totalDirectOffers;
    console.log("\x1b[34m", "Average price of direct offers: " + averageDirectOffersPrice);

    //Calculate average price of direct offers that were accepted
    let totalDirectOffersPriceAccepted = 0;
    for (let consumer of consumers) {
        let offers = await serviceOfferDirect.OfferDirect.find({seller: consumer.account, state: "ACCEPTED"});
        for (let offer of offers) {
            totalDirectOffersPriceAccepted += offer.price;
        }
    }
    let averageDirectOffersPriceAccepted = totalDirectOffersPriceAccepted / totalDirectOffersAccepted;
    console.log("\x1b[34m", "Average price of direct offers accepted: " + averageDirectOffersPriceAccepted);

    //Calculate average price of direct offers that were rejected
    let totalDirectOffersPriceRejected = 0;
    for (let consumer of consumers) {
        let offers = await serviceOfferDirect.OfferDirect.find({seller: consumer.account, state: "REJECTED"});
        for (let offer of offers) {
            totalDirectOffersPriceRejected += offer.price;
        }
    }
    let averageDirectOffersPriceRejected = totalDirectOffersPriceRejected / totalDirectOffersRejected;
    console.log("\x1b[34m", "Average price of direct offers rejected: " + averageDirectOffersPriceRejected);

    //Calculate average price of direct offers that expired
    let totalDirectOffersPriceExpired = 0;
    for (let consumer of consumers) {
        let offers = await serviceOfferDirect.OfferDirect.find({seller: consumer.account, state: "EXPIRED"});
        for (let offer of offers) {
            totalDirectOffersPriceExpired += offer.price;
        }
    }
    let averageDirectOffersPriceExpired = totalDirectOffersPriceExpired / totalDirectOffersExpired;
    console.log("\x1b[34m", "Average price of direct offers expired: " + averageDirectOffersPriceExpired);

    //Calculate cumulative cost of accepted offers per consumer and that calculate average cumulative cost of all consumers
    let totalDirectOffersPriceAcceptedCumulative = 0;
    for (let consumer of consumers) {
        let offers = await serviceOfferDirect.OfferDirect.find({seller: consumer.account, state: "ACCEPTED"});
        let cumulativePrice = 0;
        for (let offer of offers) {
            cumulativePrice += offer.price;
        }
        totalDirectOffersPriceAcceptedCumulative += cumulativePrice;
    }
    let averageDirectOffersPriceAcceptedCumulative = totalDirectOffersPriceAcceptedCumulative / consumers.length;
    console.log("\x1b[32m", "Average cost for all services: " + averageDirectOffersPriceAcceptedCumulative);

});
