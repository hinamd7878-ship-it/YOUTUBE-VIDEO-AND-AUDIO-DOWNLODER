const urlInput = document.getElementById("urlInput");

const videoBtn = document.getElementById("videoBtn");

const audioBtn = document.getElementById("audioBtn");

const clearBtn = document.getElementById("clearBtn");

const status = document.getElementById("status");

const videoContainer =
    document.getElementById("videoContainer");

const videoPlayer =
    document.getElementById("videoPlayer");

const saveBtn =
    document.getElementById("saveBtn");


// =========================================================
// CREATE PROGRESS UI
// =========================================================

let progressBox = document.getElementById(
    "progressBox"
);

if (!progressBox) {

    progressBox = document.createElement("div");

    progressBox.id = "progressBox";

    progressBox.className = "progress-box hidden";

    progressBox.innerHTML = `
        <div class="progress-top">
            <strong id="progressPercent">
                0%
            </strong>

            <span id="progressStatus">
                Starting...
            </span>
        </div>

        <div class="progress-track">
            <div
                id="progressBar"
                class="progress-bar"
            ></div>
        </div>

        <div class="progress-info">

            <span id="progressSize">
                0 MB / --
            </span>

            <span id="progressSpeed">
                0 MB/s
            </span>

            <span id="progressEta">
                ETA: --
            </span>

        </div>
    `;

    const heroCard =
        document.querySelector(".hero-card");

    if (heroCard) {
        heroCard.appendChild(progressBox);
    }
}


const progressPercent =
    document.getElementById("progressPercent");

const progressStatus =
    document.getElementById("progressStatus");

const progressBar =
    document.getElementById("progressBar");

const progressSize =
    document.getElementById("progressSize");

const progressSpeed =
    document.getElementById("progressSpeed");

const progressEta =
    document.getElementById("progressEta");


// =========================================================
// CLEAR BUTTON
// =========================================================

clearBtn.addEventListener(
    "click",
    function () {

        urlInput.value = "";

        clearBtn.style.display = "none";

        status.textContent = "";

        videoContainer.classList.add(
            "hidden"
        );

        progressBox.classList.add(
            "hidden"
        );

        videoPlayer.removeAttribute(
            "src"
        );

        videoPlayer.load();

        urlInput.focus();
    }
);


// =========================================================
// INPUT
// =========================================================

urlInput.addEventListener(
    "input",
    function () {

        clearBtn.style.display =
            urlInput.value
                ? "block"
                : "none";
    }
);


// =========================================================
// ENTER KEY
// =========================================================

urlInput.addEventListener(
    "keydown",
    function (event) {

        if (event.key === "Enter") {

            downloadFile("video");
        }
    }
);


// =========================================================
// VIDEO BUTTON
// =========================================================

videoBtn.addEventListener(
    "click",
    function () {

        downloadFile("video");
    }
);


// =========================================================
// AUDIO BUTTON
// =========================================================

audioBtn.addEventListener(
    "click",
    function () {

        downloadFile("audio");
    }
);


// =========================================================
// RESET PROGRESS
// =========================================================

function resetProgress() {

    progressBox.classList.remove(
        "hidden"
    );

    progressPercent.textContent =
        "0%";

    progressStatus.textContent =
        "Starting...";

    progressBar.style.width =
        "0%";

    progressSize.textContent =
        "0 MB / --";

    progressSpeed.textContent =
        "0 MB/s";

    progressEta.textContent =
        "ETA: --";
}


// =========================================================
// UPDATE PROGRESS
// =========================================================

function updateProgress(data) {

    let percent =
        Number(data.progress || 0);

    percent = Math.max(
        0,
        Math.min(
            100,
            percent
        )
    );


    progressPercent.textContent =
        Math.round(percent) + "%";


    progressBar.style.width =
        percent + "%";


    progressSize.textContent =
        (data.downloaded || "0 MB")
        + " / "
        + (data.total || "--");


    progressSpeed.textContent =
        data.speed || "0 MB/s";


    progressEta.textContent =
        "ETA: "
        + (data.eta || "--");


    if (
        data.status === "queued"
    ) {

        progressStatus.textContent =
            "Waiting...";
    }

    else if (
        data.status === "downloading"
    ) {

        progressStatus.textContent =
            "Downloading...";
    }

    else if (
        data.status === "processing"
    ) {

        progressStatus.textContent =
            "Processing...";
    }

    else if (
        data.status === "ready"
    ) {

        progressStatus.textContent =
            "Completed!";
    }

    else if (
        data.status === "error"
    ) {

        progressStatus.textContent =
            "Failed";
    }
}


// =========================================================
// WAIT FOR DOWNLOAD
// =========================================================

async function waitForDownload(
    jobId,
    type
) {

    const maxWait =
        30 * 60 * 1000;

    const startedAt =
        Date.now();


    while (
        Date.now() - startedAt
        < maxWait
    ) {

        try {

            const response =
                await fetch(
                    "/api/progress/"
                    + encodeURIComponent(
                        jobId
                    )
                );


            if (!response.ok) {

                throw new Error(
                    "Progress request failed."
                );
            }


            const data =
                await response.json();


            updateProgress(data);


            // =========================================
            // ERROR
            // =========================================

            if (
                data.status ===
                "error"
            ) {

                throw new Error(
                    data.error ||
                    "Download failed."
                );
            }


            // =========================================
            // READY
            // =========================================

            if (
                data.status ===
                "ready"
            ) {

                progressBar.style.width =
                    "100%";

                progressPercent.textContent =
                    "100%";

                progressStatus.textContent =
                    "Completed!";

                progressEta.textContent =
                    "Done";


                await getFinalFile(
                    jobId,
                    type
                );


                return;
            }


        }

        catch (error) {

            throw error;
        }


        // Check every 1 second

        await new Promise(
            function (resolve) {

                setTimeout(
                    resolve,
                    1000
                );
            }
        );
    }


    throw new Error(
        "Download timeout. Please try again."
    );
}


// =========================================================
// GET FINAL FILE
// =========================================================

async function getFinalFile(
    jobId,
    type
) {

    status.textContent =
        "✨ File ready ho rahi hai...";


    const response =
        await fetch(
            "/api/file/"
            + encodeURIComponent(
                jobId
            )
        );


    if (!response.ok) {

        let message =
            "File download failed.";


        try {

            const data =
                await response.json();

            message =
                data.error ||
                message;

        }

        catch {

            // Ignore JSON error
        }


        throw new Error(
            message
        );
    }


    const blob =
        await response.blob();


    const fileUrl =
        URL.createObjectURL(
            blob
        );


    // =========================================
    // VIDEO
    // =========================================

    if (
        type === "video"
    ) {

        videoPlayer.src =
            fileUrl;


        saveBtn.href =
            fileUrl;


        saveBtn.download =
            "YouTube_Video";


        videoContainer.classList.remove(
            "hidden"
        );


        status.textContent =
            "✅ Done! Video ready hai 🔥";


        videoPlayer.load();
    }


    // =========================================
    // AUDIO
    // =========================================

    else {

        const link =
            document.createElement(
                "a"
            );


        link.href =
            fileUrl;


        link.download =
            "YouTube_Audio";


        document.body.appendChild(
            link
        );


        link.click();


        link.remove();


        status.textContent =
            "✅ Done! Audio download ho gayi 🎵";


        setTimeout(
            function () {

                URL.revokeObjectURL(
                    fileUrl
                );

            },
            10000
        );
    }
}


// =========================================================
// MAIN DOWNLOAD
// =========================================================

async function downloadFile(
    type
) {

    const url =
        urlInput.value.trim();


    // =========================================
    // URL CHECK
    // =========================================

    if (!url) {

        status.textContent =
            "⚠️ YouTube URL paste karo.";

        urlInput.focus();

        return;
    }


    // =========================================
    // DISABLE BUTTONS
    // =========================================

    videoBtn.disabled =
        true;

    audioBtn.disabled =
        true;


    if (
        type === "video"
    ) {

        videoBtn.querySelector(
            ".btn-text"
        ).textContent =
            "Processing...";


        videoBtn.querySelector(
            ".btn-arrow"
        ).textContent =
            "⏳";
    }


    else {

        audioBtn.innerHTML =
            `
            <span>
                Processing...
            </span>

            <span>
                ⏳
            </span>
            `;
    }


    // =========================================
    // RESET OLD RESULT
    // =========================================

    videoContainer.classList.add(
        "hidden"
    );


    videoPlayer.removeAttribute(
        "src"
    );


    videoPlayer.load();


    resetProgress();


    status.textContent =
        type === "video"
            ? "⏳ Video download start ho rahi hai..."
            : "⏳ Audio download start ho rahi hai...";


    try {

        // =========================================
        // START JOB
        // =========================================

        const response =
            await fetch(
                "/api/download",
                {

                    method:
                        "POST",

                    headers: {

                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({

                            url:
                                url,

                            type:
                                type
                        })
                }
            );


        // =========================================
        // RESPONSE
        // =========================================

        const contentType =
            response.headers.get(
                "content-type"
            ) || "";


        if (!response.ok) {

            let message =
                "Download failed.";


            if (
                contentType.includes(
                    "application/json"
                )
            ) {

                const data =
                    await response.json();


                message =
                    data.error ||
                    message;
            }


            throw new Error(
                message
            );
        }


        const data =
            await response.json();


        // =========================================
        // JOB ID CHECK
        // =========================================

        if (
            !data.job_id
        ) {

            throw new Error(
                "Server ne download job ID nahi bheji."
            );
        }


        status.textContent =
            type === "video"
                ? "⏳ Video download ho rahi hai..."
                : "⏳ Audio download ho rahi hai...";


        // =========================================
        // START PROGRESS POLLING
        // =========================================

        await waitForDownload(
            data.job_id,
            type
        );


    }

    catch (error) {

        console.error(
            "DOWNLOAD ERROR:",
            error
        );


        progressStatus.textContent =
            "Failed";


        status.textContent =
            "❌ "
            + (
                error.message ||
                "Download failed."
            );
    }


    finally {

        // =========================================
        // ENABLE BUTTONS
        // =========================================

        videoBtn.disabled =
            false;

        audioBtn.disabled =
            false;


        videoBtn.innerHTML =
            `
            <span class="btn-text">
                Download Video
            </span>

            <span class="btn-arrow">
                →
            </span>
            `;


        audioBtn.innerHTML =
            `
            <span>
                🎵 Download Audio
            </span>

            <span>
                →
            </span>
            `;
    }
}