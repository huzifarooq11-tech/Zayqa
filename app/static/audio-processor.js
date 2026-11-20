
class PCMProcessor extends AudioWorkletProcessor {

    constructor() {

        super();

        this.buffer = [];

        // 20 milliseconds of audio at 16 kHz.
        this.targetSamples = 320;

    }


    process(inputs) {

        const input = inputs[0];


        if (!input || !input[0]) {

            return true;

        }


        const channel = input[0];

        const ratio = sampleRate / 16000;


        for (
            let i = 0;
            i < channel.length;
            i += ratio
        ) {

            const sample = Math.max(

                -1,

                Math.min(

                    1,

                    channel[Math.floor(i)]

                )

            );


            // Convert Float32 audio into Int16 PCM.

            this.buffer.push(

                sample < 0

                    ? sample * 32768

                    : sample * 32767

            );


            // Send each 20 ms audio chunk.

            if (
                this.buffer.length >= this.targetSamples
            ) {

                const pcm = new Int16Array(

                    this.buffer.splice(
                        0,
                        this.targetSamples
                    )

                );


                this.port.postMessage(

                    pcm.buffer,

                    [pcm.buffer]

                );

            }

        }


        return true;

    }

}


// Register the processor.

registerProcessor(

    "pcm-processor",

    PCMProcessor

);
