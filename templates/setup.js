
document.getElementById("spotify-sign-in-button").onclick = function () {
    var clientID = document.getElementById("client-id").value;
    var clientSecret = document.getElementById("client-secret").value;
    console.log("Hi")
    if (!clientID | !clientSecret) {
        document.getElementById("missing-modal").modal("show");
    }
    location.href = `/attempt-login?client-id=${clientID.value}&client-secret=${clientSecret.value}`
}