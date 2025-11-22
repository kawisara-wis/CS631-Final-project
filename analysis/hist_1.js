const config = require('../config.json');

const {mongoose} = require('mongoose');
const serviceConsumer = require("../services/Consumer");
const serviceService = require("../services/Service");
const serviceOfferDirect = require("../services/OfferDirect");
const ChartJSImage = require('chart.js-image');

mongoose.connect(config.db.url).then(async () => {
    //Analyse consumers
    let consumers = await serviceConsumer.Consumer.find({});

    //Write to console in blue number of consumers
    console.log("\x1b[34m", "CONSUMERS");
    console.log("\x1b[34m", "Number of consumers: " + consumers.length);

    // Calculate data for histogram
    let data = [];
    for (let consumer of consumers) {
        let offers = await serviceOfferDirect.OfferDirect.find({seller: consumer.account});
        offers.forEach(offer => data.push(offer.price));
    }

    data.sort((a, b) => a - b);

    let minPrice = Math.min(...data);
    let maxPrice = Math.max(...data);
    const binSize = 1; // Example bin size, adjust as needed
    const binCount = Math.ceil((maxPrice - minPrice) / binSize);

    let bins = new Array(binCount).fill(0);
    let labels = new Array(binCount).fill(0).map((_, index) => `${minPrice + index * binSize} - ${minPrice + (index + 1) * binSize}`);

// Count prices into bins
    for (let price of data) {
        let binIndex = Math.floor((price - minPrice) / binSize);
        bins[binIndex]++;
    }

    // Create and configure a bar chart to simulate a histogram
    const chart = ChartJSImage().chart({
        type: 'bar',
        data: {
            labels: labels, // Use the bin labels
            datasets: [{
                label: 'Offer Prices',
                data: bins, // Use the bin counts
                backgroundColor: 'rgba(255, 99, 132, 0.2)',
                borderColor: 'rgba(255, 99, 132, 1)',
                borderWidth: 1
            }]
        },
        options: {
            scales: {
                x: {
                    title: {
                        display: true,
                        text: 'Price Range'
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: 'Number of Offers'
                    },
                    beginAtZero: true
                }
            }
        }
    }).backgroundColor('white').width(800).height(600);

    // Save histogram to file
    await chart.toFile('histogram.png');
    console.log("\x1b[34m", "Histogram saved to histogram.png");
});
